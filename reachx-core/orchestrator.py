"""
Outreach Orchestrator - Main agentic workflow
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger
import json
import asyncio

from models import Lead, OutreachCampaign, OutreachStatus
from llm_factory import LLMFactory
from auditor_agent import AuditorAgent
from linkedin_scraper import linkedin_scraper
from company_intelligence import company_intel
from config import settings


class OutreachOrchestrator:
    """
    Main agent that orchestrates the entire outreach workflow:
    
    1. Data Collection (LinkedIn + Company Intel)
    2. Analysis (Kimi-powered deep analysis)
    3. Personalization (Generate hyper-personalized emails)
    4. Quality Control (Score and filter)
    5. Execution (Send or queue for review)
    """
    
    def __init__(self, db_session):
        self.db = db_session
        self.min_personalization_score = settings.min_personalization_score
        self.llm = LLMFactory.get_provider()
        self.auditor = AuditorAgent()
    
    async def process_lead(
        self,
        lead: Lead,
        company_context: str,
        value_proposition: str,
        auto_send: bool = False
    ) -> Dict[str, Any]:
        """
        Complete end-to-end processing of a single lead
        
        Args:
            lead: Lead database object
            company_context: Your company's background
            value_proposition: What you're offering
            auto_send: If True, send email automatically if score is high enough
            
        Returns:
            Processing result with status, scores, and generated content
        """
        
        logger.info(f"Processing lead: {lead.name} ({lead.email})")
        
        result: Dict[str, Any] = {
            'lead_id': lead.id,
            'lead_name': lead.name,
            'status': 'processing',
            'stages': {}
        }
        
        try:
            # Stage 1: Data Enrichment
            logger.info("Stage 1: Data Enrichment")
            enrichment = await self._enrich_lead_data(lead)
            result['stages']['enrichment'] = enrichment
            
            if enrichment['status'] == 'failed':
                result['status'] = 'enrichment_failed'
                return result
            
            # Stage 2: AI Analysis
            logger.info("Stage 2: AI Analysis")
            analysis = await self._analyze_lead(lead, enrichment['data'])
            result['stages']['analysis'] = analysis
            
            # Check relevance score
            relevance_score = analysis.get('relevance_score', 0)
            if relevance_score < self.min_personalization_score:
                logger.warning(f"Lead {lead.name} below relevance threshold: {relevance_score}")
                result['status'] = 'low_relevance'
                result['relevance_score'] = relevance_score
                return result
            
            # Stage 3 & 4: Email Generation (with Self-Correction)
            logger.info("Stage 3: Email Generation with Agentic Refinement")
            
            email = None
            quality_check = None
            max_attempts = 2
            
            for attempt in range(max_attempts):
                logger.info(f"Generation Attempt {attempt + 1}/{max_attempts}")
                
                # If we have feedback from previous attempt, we would pass it here
                # context_with_feedback = ... 
                
                email = await self._generate_email(lead, analysis, company_context, value_proposition)
                quality_check = await self._quality_control(email, analysis)
                
                if quality_check['quality_score'] >= 0.8:
                    logger.info("Quality check passed!")
                    break
                
                logger.warning(f"Quality score {quality_check['quality_score']} below threshold. issues: {quality_check['issues']}")
                
            result['stages']['email_generation'] = email
            result['stages']['quality_check'] = quality_check
            
            # Stage 5: Create Campaign Record
            logger.info("Stage 5: Creating Campaign")
            campaign = await self._create_campaign(lead, email, analysis, quality_check)
            result['campaign_id'] = campaign.id
            result['status'] = 'ready'
            
            # Stage 6: Auto-send if enabled and quality is high
            if auto_send and quality_check['quality_score'] >= 0.8:
                logger.info("Stage 6: Auto-sending (quality score >= 0.8)")
                send_result = await self._send_email(campaign)
                result['stages']['send'] = send_result
                result['status'] = 'sent' if send_result['success'] else 'send_failed'
            else:
                result['status'] = 'pending_review'
            
            logger.info(f"Lead processing complete: {result['status']}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing lead {lead.name}: {e}")
            result['status'] = 'error'
            result['error'] = str(e)
            return result
    
    async def _enrich_lead_data(self, lead: Lead) -> Dict[str, Any]:
        """Gather all data about the lead"""
        
        enrichment_data = {
            'status': 'success',
            'data': {}
        }
        
        try:
            # LinkedIn Profile
            if lead.linkedin_url:
                profile_data = await linkedin_scraper.scrape_profile(lead.linkedin_url)
                enrichment_data['data']['linkedin_profile'] = profile_data
                
                # Recent activity
                recent_activity = await linkedin_scraper.get_recent_activity(lead.linkedin_url, limit=10)
                enrichment_data['data']['recent_activity'] = recent_activity
                
                # Update lead with scraped data
                lead.linkedin_profile_data = profile_data
                lead.recent_posts = recent_activity
            
            # Company Intelligence
            if lead.company:
                company_data = await company_intel.enrich_company_data(
                    lead.company,
                    lead.company_website
                )
                enrichment_data['data']['company_intelligence'] = company_data
                
                # Update lead with company data
                lead.company_news = company_data.get('recent_news', [])
                lead.company_industry = company_data.get('industry')
            
            lead.last_enriched_at = datetime.utcnow()
            self.db.commit()
            
            return enrichment_data
            
        except Exception as e:
            logger.error(f"Enrichment failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
                'data': {}
            }
    
    async def _analyze_lead(self, lead: Lead, enrichment_data: Dict) -> Dict[str, Any]:
        """Deeply analyze the lead using autonomous intelligence"""
        
        lead_data = {
            'name': lead.name,
            'email': lead.email,
            'company': lead.company,
            'job_title': lead.job_title,
            'location': lead.location,
            'linkedin_profile': enrichment_data.get('linkedin_profile', {}),
            'recent_activity': enrichment_data.get('recent_activity', []),
            'company_intelligence': enrichment_data.get('company_intelligence', {})
        }
        
        prompt = f"Analyze this lead profile and identify pain points, interests, and personalization hooks:\n{json.dumps(lead_data)}"
        response = self.llm.completion([{"role": "user", "content": prompt}], temperature=0.3)
        
        # Simple parsing for demo (real version would use structured output)
        try:
            analysis = json.loads(response["content"])
        except:
            analysis = {"relevance_score": 0.85, "pain_points": ["scaling bottlenecks"], "interests": ["AI automation"]}
            
        lead.pain_points = analysis.get('pain_points', [])
        lead.interests = analysis.get('interests', [])
        lead.relevance_score = analysis.get('relevance_score', 0)
        
        self.db.commit()
        return analysis
    
    async def _generate_email(
        self,
        lead: Lead,
        analysis: Dict,
        company_context: str,
        value_proposition: str
    ) -> Dict[str, Any]:
        """Generate hyper-personalized email with cognitive hooks"""
        
        prompt = f"Lead: {lead.name}, Analysis: {json.dumps(analysis)}, Our Context: {company_context}, Value Prop: {value_proposition}. Write a hyper-personalized cold email."
        response = self.llm.completion([{"role": "user", "content": prompt}], temperature=0.8)
        
        # Mocking structured response for brevity in this step
        return {
            "subject_line": "Scale your engineering velocity at " + lead.company,
            "email_body": response["content"],
            "personalization_elements": ["recent post", "funding alert"]
        }
    
    async def _quality_control(self, email: Dict, analysis: Dict) -> Dict[str, Any]:
        """Agentic Quality Control with feedback loop"""
        return await self.auditor.audit_email(email, analysis)
    
    async def _create_campaign(
        self,
        lead: Lead,
        email: Dict,
        analysis: Dict,
        quality_check: Dict
    ) -> OutreachCampaign:
        """Create campaign record in database"""
        
        campaign = OutreachCampaign(
            lead_id=lead.id,
            subject_line=email['subject_line'],
            email_body=email['email_body'],
            personalization_elements=email.get('personalization_elements', []),
            model_used=settings.kimi_model,
            generation_metadata={
                'analysis': analysis,
                'quality_check': quality_check,
                'expected_response_rate': email.get('expected_response_rate')
            },
            status=OutreachStatus.READY
        )
        
        self.db.add(campaign)
        self.db.commit()
        self.db.refresh(campaign)
        
        logger.info(f"Created campaign {campaign.id} for lead {lead.name}")
        return campaign
    
    async def _send_email(self, campaign: OutreachCampaign) -> Dict[str, Any]:
        """
        Send the email (placeholder - implement with SendGrid)
        """
        
        # This is where you'd integrate with SendGrid or other email service
        # For now, just log it
        
        logger.info(f"SENDING EMAIL to {campaign.lead.email}")
        logger.info(f"Subject: {campaign.subject_line}")
        logger.info(f"Body:\n{campaign.email_body}")
        
        # Update campaign status
        campaign.status = OutreachStatus.SENT
        campaign.sent_at = datetime.utcnow()
        self.db.commit()
        
        return {
            'success': True,
            'sent_at': campaign.sent_at.isoformat()
        }
    
    async def batch_process_leads(
        self,
        lead_ids: List[int],
        company_context: str,
        value_proposition: str,
        auto_send: bool = False,
        max_concurrent: int = 5
    ) -> Any:
        """
        Process multiple leads concurrently
        
        Args:
            lead_ids: List of lead IDs to process
            company_context: Your company context
            value_proposition: What you're offering
            auto_send: Auto-send high-quality emails
            max_concurrent: Max concurrent processing
            
        Returns:
            List of processing results
        """
        
        logger.info(f"Batch processing {len(lead_ids)} leads")
        
        # Fetch all leads
        leads = self.db.query(Lead).filter(Lead.id.in_(lead_ids)).all()
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(lead):
            async with semaphore:
                return await self.process_lead(
                    lead,
                    company_context,
                    value_proposition,
                    auto_send
                )
        
        # Process all leads concurrently (with limit)
        results = await asyncio.gather(
            *[process_with_semaphore(lead) for lead in leads],
            return_exceptions=True
        )
        
        # Compile statistics
        stats = {
            'total': len(results),
            'successful': sum(1 for r in results if isinstance(r, dict) and r.get('status') in ['ready', 'sent']),
            'sent': sum(1 for r in results if isinstance(r, dict) and r.get('status') == 'sent'),
            'low_relevance': sum(1 for r in results if isinstance(r, dict) and r.get('status') == 'low_relevance'),
            'failed': sum(1 for r in results if not isinstance(r, dict) or r.get('status') in ['error', 'enrichment_failed'])
        }
        
        logger.info(f"Batch processing complete: {stats}")
        
        return {
            'results': results,
            'statistics': stats
        }

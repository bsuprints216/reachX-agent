from typing import Dict, List, Any
from loguru import logger
import json
from llm_factory import LLMFactory

class AuditorAgent:
    """
    Agentic Auditor - Scores and provides feedback for generated content
    """
    
    def __init__(self, provider: str = "deepseek"):
        self.llm = LLMFactory.get_provider(provider)

    async def audit_email(self, email: Dict, analysis: Dict) -> Dict[str, Any]:
        """
        Perform a deep audit of the generated email
        """
        prompt = f"""
You are a senior sales copy editor at a top tech firm. Audit this cold outreach email.

**Context:**
- Lead Analysis: {json.dumps(analysis)}
- Subject: {email['subject_line']}
- Body: {email['email_body']}

**Audit Criteria (0-10 scale for each):**
1. Personalization: Does it reference specific context?
2. Value Proposition: Is the benefit clear and tailored?
3. Concise: Is it under 150 words?
4. CTA: Is there a low-friction next step?
5. Tone: Is it professional yet human? (No AI fluff)

Return JSON:
{{
  "scores": {{ "personalization": 0, "value": 0, "conciseness": 0, "cta": 0, "tone": 0 }},
  "overall_score": 0.0-1.0,
  "issues": ["issue1", ...],
  "feedback": "Specific feedback for improvement",
  "approved": true/false
}}
"""
        messages = [{"role": "system", "content": "You are a ruthless but constructive sales copy auditor."},
                    {"role": "user", "content": prompt}]
        
        response = self.llm.completion(messages, temperature=0.2)
        
        try:
            content = response["content"]
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            return json.loads(content)
        except Exception as e:
            logger.error(f"Audit failed: {e}")
            return { "overall_score": 0.5, "approved": False, "issues": ["Audit processing error"] }

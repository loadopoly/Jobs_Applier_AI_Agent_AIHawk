import json
from typing import Dict, Any, List
from src.libs.llm_manager import AIAdapter
from src.logging import logger

class RecruiterPrepEngine:
    def __init__(self, ai_adapter: AIAdapter):
        self.ai_adapter = ai_adapter

    def generate_briefing(self, company_name: str, job_role: str, resume_yaml_path: str) -> Dict[str, Any]:
        """
        Generates a 'cheat sheet' for the candidate to use when speaking with a recruiter.
        """
        try:
            with open(resume_yaml_path, 'r') as f:
                resume_content = f.read()
        except Exception as e:
            logger.error(f"Failed to read resume at {resume_yaml_path}: {e}")
            return {}

        prompt = f"""
        You are an expert Interview Coach. A candidate is about to speak with a recruiter from '{company_name}' for the position of '{job_role}'.
        
        CANDIDATE RESUME:
        {resume_content}

        Generate a 'Recruiter Briefing Card' in JSON format with:
        - company_mission: A 1-sentence probable mission/value proposition for {company_name}.
        - elevator_pitch: A 30-second 'Why me?' pitch tailored to this company and role.
        - interview_questions: 3 high-impact questions the candidate should ask the recruiter.
        - potential_weakness_counter: 1 potential weakness in the resume for this role and how to address it positively.
        - recent_industry_context: 1-2 sentences of general industry context/trends relevant to {company_name}.

        Return ONLY the JSON.
        """
        
        try:
            logger.info(f"Generating briefing card for {company_name}...")
            response = self.ai_adapter.invoke(prompt)
            content = getattr(response, 'content', str(response))
            
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            return json.loads(content)
        except Exception as e:
            logger.error(f"Error generating recruiter briefing: {e}")
            return {
                "company_mission": f"A major player in its industry.",
                "elevator_pitch": f"I'm a strong candidate for {job_role} with relevant experience.",
                "interview_questions": [
                    "What does success look like in this role?",
                    "How does the team handle collaboration?",
                    "What are the immediate priorities for this position?"
                ],
                "potential_weakness_counter": "Focus on your strengths and ability to learn quickly.",
                "recent_industry_context": "The industry is evolving rapidly with a focus on automation and efficiency."
            }

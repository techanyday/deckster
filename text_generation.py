from openai import OpenAI
from typing import Dict, List
import os
import httpx

class TextGenerator:
    def __init__(self):
        """Initialize the OpenAI text generator."""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OpenAI API key not found in environment variables")
        self.client = OpenAI(
            api_key=api_key,
            http_client=httpx.Client(timeout=30.0)
        )

    def generate_slide_content(self, topic: str, max_slides: int = 5) -> Dict[str, List[str]]:
        """Generate content for PowerPoint slides based on the given topic."""
        try:
            # Create a structured prompt for ChatGPT
            system_prompt = """You are a professional presentation creator. Create clear, engaging, and informative presentation content."""
            
            user_prompt = f"""Create a presentation about: {topic}

            Requirements:
            1. Generate exactly {max_slides} slides
            2. Each slide should have:
               - A clear, specific title
               - 3-4 detailed bullet points that support the title
            3. Content should be:
               - Professional and accurate
               - Easy to understand
               - Logically structured
               - Free of repetition
            4. Do not include basic definitions or obvious statements
            5. Include specific examples and real-world applications

            Format the response exactly as follows:
            Title: [Presentation Title]

            Slide 1: [Slide Title]
            - [Bullet Point 1]
            - [Bullet Point 2]
            - [Bullet Point 3]

            Slide 2: [Slide Title]
            [Continue for all slides...]"""

            # Call ChatGPT API
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )

            # Process the response
            content = response.choices[0].message.content
            
            # Parse the content into our required format
            lines = content.strip().split('\n')
            results = {
                "title": [],
                "outline": [],
                "content": []
            }
            
            current_title = None
            current_points = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith('Title:'):
                    results['title'] = [line.split('Title:')[1].strip()]
                elif line.startswith('Slide'):
                    if current_title and current_points:
                        results['content'].extend([current_title] + current_points)
                    current_title = line.split(':', 1)[1].strip()
                    results['outline'].append(current_title)
                    current_points = []
                elif line.startswith('-'):
                    point = line[1:].strip()
                    if point:
                        current_points.append(point)
            
            # Add the last slide
            if current_title and current_points:
                results['content'].extend([current_title] + current_points)

            return results

        except Exception as e:
            print(f"Error generating content: {str(e)}")  
            raise Exception(f"Error generating content: {str(e)}")

    def __call__(self, topic: str, max_slides: int = 5) -> Dict[str, List[str]]:
        """Convenience method to generate slide content."""
        return self.generate_slide_content(topic, max_slides)

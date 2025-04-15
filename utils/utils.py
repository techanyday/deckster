import os
import tempfile
from datetime import datetime, timedelta
from models import SubscriptionPlan, Presentation
from openai import OpenAI
from pptx import Presentation as PPTXPresentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from PIL import Image, ImageDraw

def check_user_limits(user):
    """Check if user has reached their presentation limits."""
    plan = SubscriptionPlan.PLANS.get(user.subscription_type, SubscriptionPlan.PLANS['free'])
    
    # Get the time window based on subscription type
    if user.subscription_type == 'free':
        time_window = datetime.utcnow() - timedelta(weeks=1)
    else:
        time_window = datetime.utcnow() - timedelta(days=30)
    
    # Count presentations in the time window
    presentation_count = Presentation.query.filter(
        Presentation.user_id == user.id,
        Presentation.created_at >= time_window
    ).count()
    
    return presentation_count < plan['presentations_limit']

def get_max_slides(user):
    """Get maximum number of slides allowed for user's plan."""
    plan = SubscriptionPlan.PLANS.get(user.subscription_type, SubscriptionPlan.PLANS['free'])
    return plan['max_slides']

def generate_presentation_content(mode, input_text):
    """Generate presentation content using OpenAI."""
    client = OpenAI()
    
    if mode == 'prompt':
        system_prompt = """You are a presentation expert. Create a well-structured presentation outline based on the given topic.
        Format each slide as: 'Slide N: Title\nContent' where N is the slide number.
        Keep content concise and impactful."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Create a presentation about: {input_text}"}
        ]
    else:  # content mode
        system_prompt = """You are a presentation expert. Convert the given content into a well-structured presentation outline.
        Format each slide as: 'Slide N: Title\nContent' where N is the slide number.
        Maintain key points while making content concise and impactful."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Convert this content into a presentation:\n{input_text}"}
        ]
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error generating content: {str(e)}")
        return None

def create_ppt(content, template='modern', custom_styles=None):
    """Create a PowerPoint presentation from the generated content."""
    prs = PPTXPresentation()
    
    # Set default styles based on template
    styles = get_template_styles(template)
    if custom_styles:
        styles.update(custom_styles)
    
    slides = content.split('\n\n')
    
    for slide_text in slides:
        if not slide_text.strip():
            continue
            
        # Parse slide title and content
        parts = slide_text.split('\n', 1)
        if len(parts) != 2:
            continue
            
        title = parts[0].replace('Slide {}: '.format(len(prs.slides) + 1), '').strip()
        content = parts[1].strip()
        
        # Add slide
        slide = prs.slides.add_slide(prs.slide_layouts[1])  # Title and Content layout
        
        # Set title
        title_shape = slide.shapes.title
        title_shape.text = title
        title_shape.text_frame.paragraphs[0].font.size = Pt(40)
        title_shape.text_frame.paragraphs[0].font.color.rgb = RGBColor(*hex_to_rgb(styles['title_color']))
        
        # Set content
        content_shape = slide.placeholders[1]
        content_shape.text = content
        for paragraph in content_shape.text_frame.paragraphs:
            paragraph.font.size = Pt(24)
            paragraph.font.color.rgb = RGBColor(*hex_to_rgb(styles['text_color']))
        
        # Set background
        background = slide.background
        fill = background.fill
        if styles['background']['type'] == 'solid':
            fill.solid()
            fill.fore_color.rgb = RGBColor(*hex_to_rgb(styles['background']['color']))
        elif styles['background']['type'] == 'gradient':
            fill.gradient()
            fill.gradient_stops[0].color.rgb = RGBColor(*hex_to_rgb(styles['background']['color1']))
            fill.gradient_stops[1].color.rgb = RGBColor(*hex_to_rgb(styles['background']['color2']))
    
    return prs

def get_template_styles(template):
    """Get predefined styles for a template."""
    templates = {
        'modern': {
            'title_color': '#333333',
            'text_color': '#666666',
            'background': {
                'type': 'gradient',
                'color1': '#FFFFFF',
                'color2': '#F5F5F5'
            }
        },
        'nature': {
            'title_color': '#2E7D32',
            'text_color': '#333333',
            'background': {
                'type': 'gradient',
                'color1': '#FFFFFF',
                'color2': '#E8F5E9'
            }
        },
        'ocean': {
            'title_color': '#1565C0',
            'text_color': '#333333',
            'background': {
                'type': 'gradient',
                'color1': '#FFFFFF',
                'color2': '#E3F2FD'
            }
        },
        'sunset': {
            'title_color': '#E65100',
            'text_color': '#333333',
            'background': {
                'type': 'gradient',
                'color1': '#FFFFFF',
                'color2': '#FFF3E0'
            }
        }
    }
    return templates.get(template, templates['modern'])

def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def add_watermark(prs):
    """Add watermark to all slides for free users."""
    watermark_text = "Created with PowerPoint Generator"
    
    for slide in prs.slides:
        # Create a textbox for the watermark
        left = Inches(0)
        top = Inches(6.5)  # Bottom of the slide
        width = Inches(10)
        height = Inches(0.5)
        
        textbox = slide.shapes.add_textbox(left, top, width, height)
        textbox.text = watermark_text
        
        # Style the watermark
        text_frame = textbox.text_frame
        paragraph = text_frame.paragraphs[0]
        paragraph.alignment = 1  # Center
        paragraph.font.size = Pt(12)
        paragraph.font.color.rgb = RGBColor(169, 169, 169)  # Light gray

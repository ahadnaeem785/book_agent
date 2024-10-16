import streamlit as st
from fpdf import FPDF
from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph.state import CompiledStateGraph
from langchain.output_parsers import PydanticOutputParser
from langgraph.constants import Send
from typing import List, Annotated
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from IPython.display import Image, display
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.output_parsers import PydanticOutputParser
import json
import operator
from dotenv import load_dotenv
from langchain_groq import ChatGroq

llm = ChatGroq(
    model="llama-3.1-70b-versatile",
    temperature=0.0,
    api_key = "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",


)
# Load environment variables
load_dotenv()


# Define models for Topic, Chapter, TOC, and the entire TocAndContentState
class Topic(BaseModel):
    topic_id: str           # Unique ID for each topic
    topic_title: str        # Title of the topic
    topic_number: float     # Number of the topic (e.g., 1.1, 1.2)

class Chapter(BaseModel):
    chapter_id: str         # Unique ID for each chapter
    chapter_title: str      # Title of the chapter
    chapter_number: int     # Number of the chapter (e.g., 1, 2, 3)
    topics: List[Topic]     # List of topics within the chapter

class TOC(BaseModel):
    toc_id: str             # Unique ID for the TOC
    title: str              # Title of the Table of Contents
    description: str        # Short description of the TOC
    chapters: List[Chapter] # List of chapters

class ChapterContent(BaseModel):
    content_id: str                 # Unique ID for the chapter content
    chapter_id: str                 # Chapter ID to which this content belongs
    content_text: str               # The content for the entire chapter (overview/introduction)

class TopicContent(BaseModel):
    content_id: str                 # Unique ID for the topic content
    chapter_id: str                 # Chapter ID to which this content belongs
    topic_id: str                   # Topic ID to which this content belongs
    content_text: str               # The generated content for the topic/subtopic

class TocAndContentState(TypedDict):
    title: str              # TOC title for reference
    toc: TOC                # Table of contents
    max_chapters: int       # Max chapters
    human_toc_feedback: str # Human feedback on the TOC
    chapter_content: Annotated[List[ChapterContent], operator.add] # List of generated chapter content
    topic_content: Annotated[List[TopicContent], operator.add]     # Generated topic content

class ContentState(TypedDict):
  topic: str
  chapter_id: str
  topic_id: str




import streamlit as st
from fpdf import FPDF

# Ensure state is initialized in the session
if 'state' not in st.session_state:
    st.session_state.state = {}

if 'toc_finalized' not in st.session_state:
    st.session_state.toc_finalized = False

if 'feedback_submitted' not in st.session_state:
    st.session_state.feedback_submitted = False




TOC_instruction = """

You are required to create TOC. Follow these steps exactly and ensure the output meets the specified format.

---


### **Step-by-Step Instructions:**

1. **Review the Title:**
   - Review the following title provided by the user:
     - `{title}`
   - All chapters and topics must be relevant to this title.

2. **Analyze Editorial Feedback:**
   - If any feedback is provided, review it carefully:
     - `{human_feedback}`
   - Use this feedback to shape the focus of the chapters and topics in the Table of Contents. If no feedback is given, prioritize the general relevance of the provided title.

3. **Identify and Select Key Chapters:**
   - Analyze the title and any feedback to extract significant themes or sections.
   - Select the top `{max_chapters}` chapters based on the relevance to the title.
   - Each chapter must represent a distinct, critical aspect of the title.

4. **Create the Table of Contents:**
   - For each selected chapter, create corresponding topics.
   - The Table of Contents must include the following information:
     - **Chapter Title**: A clear title for each chapter that represents the main idea or theme.
     - **Chapter Number**: The numerical order of the chapter (e.g., 1, 2, 3).
     - **Topic Title**: A descriptive title for each topic within the chapter.
     - **Topic Number**: The numerical order of the topic within the chapter (e.g., 1.1, 1.2).

---

**Output Format – Mandatory Requirements:**

- The output **must** be in valid JSON format.
- The JSON must include the following structure:
  - A key `"toc_id"` for a unique identifier of the Table of Contents.
  - A key `"title"` for the Table of Contents title.
  - A key `"description"` for a short description of the Table of Contents.
  - A key `"chapters"` which is an array (list) of chapter objects.
  - Each chapter object must contain the following fields:
    - `"chapter_id"`: Unique ID for each chapter.
    - `"chapter_title"`: Title of the chapter.
    - `"chapter_number"`: Number of the chapter.
    - `"topics"`: An array (list) of topic objects.
      - `"topic_id"`: Unique ID for each topic.
      - `"topic_title"`: Title of the topic.
      - `"topic_number"`: Number of the topic.

The exact output format is as follows:

```
{{
  "toc_id": "string",         // Unique ID for the TOC
  "title": "string",          // Title of the Table of Content
  "description": "string",    // Short description of the TOC
  "chapters": [
    {{
      "chapter_id": "string",   // Unique ID for each chapter
      "chapter_title": "string", // Title of the chapter
      "chapter_number": "integer", // Number of the chapter (e.g., 1, 2, 3)
      "topics": [
        {{
          "topic_id": "string",   // Unique ID for each topic
          "topic_title": "string", // Title of the topic
          "topic_number": "float" // Number of the topic (e.g., 1.1, 1.2)
        }}
      ]
    }}
  ]
}}
```

"""

content_generation_prompt = """
You are tasked with generating insightful content for the following topic.

Your goal is to produce a concise and meaningful explanation under 1000 words, focusing on both **interesting** and **specific** insights.

1. **Interesting**: Provide insights that people will find surprising or non-obvious.
2. **Specific**: Avoid generalities and offer specific examples or details related to the topic.

Here is your **topic**: {topic}

Based on this topic, generate content that offers unique insights and useful information. Ensure the response is under 1000 words.

When you're satisfied with the content, conclude with: "This is a focused insight on the topic."

Make sure your content is concise, reflective of the topic, and meets the word limit requirement."""



# Function to generate content by invoking LLM
def generate_content(topic: str):
    """Node to generate content dynamically using LLM."""
    content = llm.invoke([HumanMessage(content=content_generation_prompt.format(topic=topic))])
    return content.content

# Step 1: Generate Content Functionality for the TOC Chapters and Topics
def generate_content_for_toc(state):
    """Generate content dynamically for all chapters and topics in the TOC."""
    chapter_content = []
    topic_content = []

    # Loop through each chapter and generate content
    for chapter in state['toc'].chapters:
        chapter_data = {
            'topic': chapter.chapter_title,
            'chapter_id': chapter.chapter_id
        }
        chapter_result = generate_chapter_content(chapter_data)
        chapter_content.append(chapter_result['chapter_content'][0])

        # Loop through each topic in the chapter
        for topic in chapter.topics:
            topic_data = {
                'topic': topic.topic_title,
                'chapter_id': chapter.chapter_id,
                'topic_id': topic.topic_id
            }
            topic_result = generate_topic_content(topic_data)
            topic_content.append(topic_result['topic_content'][0])

    return chapter_content, topic_content

# Function to create the TOC using LLM
def create_Toc(state: TocAndContentState):
    """Generate TOC using LLM."""
    title = state['title']
    max_chapters = state['max_chapters']
    human_toc_feedback = state.get('human_toc_feedback', '')

    system_message = TOC_instruction.format(title=title, human_feedback=human_toc_feedback, max_chapters=max_chapters)
    Toc = llm.invoke([SystemMessage(content=system_message)] + [HumanMessage(content="Generate the TOC.")])

    try:
        response_dict = PydanticOutputParser(pydantic_object=TOC).parse(Toc.content)
        if not response_dict.chapters:
            raise ValueError("TOC does not contain any chapters.")
        return {"toc": response_dict}
    except json.JSONDecodeError as e:
        st.error(f"Error decoding JSON: {e}")
        return {}

# Function to generate chapter content dynamically
def generate_chapter_content(state: ContentState):
    try:
        content = generate_content(state['topic'])
        chapter_content = ChapterContent(
            content_id=f"content_{state['chapter_id']}",
            chapter_id=state["chapter_id"],
            content_text=content
        )
        return {"chapter_content": [chapter_content]}
    except Exception as e:
        st.error(f"Error generating content for chapter {state['chapter_id']}: {e}")
        return {}

# Function to generate topic content dynamically
def generate_topic_content(state: ContentState):
    try:
        content = generate_content(state['topic'])
        topic_content = TopicContent(
            content_id=f"content_{state['topic_id']}",
            chapter_id=state['chapter_id'],
            topic_id=state['topic_id'],
            content_text=content
        )
        return {"topic_content": [topic_content]}
    except Exception as e:
        st.error(f"Error generating content for topic {state['topic_id']}: {e}")
        return {}

# Function to publish the book as a PDF instead of GitHub
def publish_book_as_pdf(state: TocAndContentState, file_name: str):
    """Publishes the book's TOC, chapters, and topics as a PDF with enhanced formatting."""
    
    # Initialize PDF object
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Set book title
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(200, 10, txt=state['title'], ln=True, align='C')
    pdf.ln(10)

    # Table of Contents
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(200, 10, txt="Table of Contents", ln=True)
    
    for chapter in state['toc'].chapters:
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(200, 10, txt=f"Chapter {chapter.chapter_number}: {chapter.chapter_title}", ln=True)
        pdf.ln(5)
        pdf.set_font('Arial', '', 12)
        for topic in chapter.topics:
            pdf.cell(200, 10, txt=f"   {topic.topic_number} - {topic.topic_title}", ln=True)
        pdf.ln(5)

    # Add content for chapters and topics
    for chapter_content in state['chapter_content']:
        pdf.add_page()
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(200, 10, txt=f"Chapter: {chapter_content.chapter_id}", ln=True)
        pdf.set_font('Arial', '', 12)
        pdf.multi_cell(0, 10, chapter_content.content_text)

    for topic_content in state['topic_content']:
        pdf.add_page()
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(200, 10, txt=f"Topic: {topic_content.topic_id}", ln=True)
        pdf.set_font('Arial', '', 12)
        pdf.multi_cell(0, 10, topic_content.content_text)

    # Save PDF
    pdf.output(file_name)
    return file_name

# Step 1: Enter Topic
topic = st.text_input("Enter the topic to generate TOC", "")

# Step 2: Generate TOC
if st.button("Generate TOC") and not st.session_state.feedback_submitted:
    # Initialize state if it doesn't exist
    st.session_state.state = {
        'title': topic,
        'max_chapters': 2  # Set this value as per your need
    }
    toc_data = create_Toc(st.session_state.state)
    if toc_data:
        st.session_state.state.update(toc_data)
        st.session_state.feedback_submitted = False  # Reset feedback submitted
        st.write("Table of Contents generated:")
        st.write(st.session_state.state['toc'])

        # Allow human feedback
        feedback = st.text_area("Provide feedback for TOC (Optional)", "")
        st.session_state.state['human_toc_feedback'] = feedback

        # Submit feedback
        if st.button("Submit Feedback"):
            if feedback:
                toc_data = create_Toc(st.session_state.state)  # Recreate TOC based on feedback
                st.session_state.state.update(toc_data)
                st.session_state.feedback_submitted = True
                st.write("Updated Table of Contents after feedback:")
                st.write(st.session_state.state['toc'])
            else:
                st.session_state.toc_finalized = True
                st.success("TOC finalized. You can now generate content.")

# Step 3: Generate Content after TOC is finalized
if st.session_state.toc_finalized or st.session_state.feedback_submitted:
    if st.button("Generate Content"):
        # Generate content dynamically for all chapters and topics in the TOC
        st.write("Generating content for chapters and topics...")
        chapter_content, topic_content = generate_content_for_toc(st.session_state.state)
        
        # Store the generated content in session state
        st.session_state.state['chapter_content'] = chapter_content
        st.session_state.state['topic_content'] = topic_content

        st.success("Content generated successfully!")

    # Step 4: Download PDF after content generation
    if 'chapter_content' in st.session_state.state and 'topic_content' in st.session_state.state:
        pdf_file = publish_book_as_pdf(st.session_state.state, "Generated_Book.pdf")
        st.success(f"PDF generated! You can download it below.")
        with open(pdf_file, "rb") as pdf:
            st.download_button(label="Download PDF", data=pdf, file_name="Generated_Book.pdf", mime="application/pdf")

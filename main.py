import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from uuid import uuid4
from typing import Optional
from contextlib import contextmanager
from transformers import pipeline
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, render_template
from sqlalchemy import create_engine, Column, String, Text, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()
# Database configuration
Base = declarative_base()

client = OpenAI(
    # This is the default and can be omitted
    api_key=os.getenv("OPENAI_API_KEY"),
)

class Research(Base):
    __tablename__ = 'researches_tbl'  # Replace with your actual table name
    id: str = Column(String, primary_key=True)
    title: Optional[str] = Column(String)
    abstract: Optional[str] = Column(Text)
    file_name: str = Column(String)
    summary: Optional[str] = Column(Text)
    
    def to_dict(self):
        """
        Converts the Research object to a dictionary.
        """
        return {
            'id': self.id,
            'title': self.title,
            'abstract': self.abstract,
            'file_name': self.file_name,
            'summary': self.summary,
        }

class Feedback(Base):
    __tablename__ = 'feedbacks_tbl'
    id: str = Column(String, primary_key=True)
    question_asked: str = Column(String)
    answer: Optional[str] = Column(Text)
    bullet_points: Optional[str] = Column(String)
    test_question: str = Column(String)
    
    def __init__(self, question_asked, answer, bullet_points, test_question):
        self.question_asked = question_asked
        self.answer = answer
        self.bullet_points = json.dumps(bullet_points)
        self.test_question = test_question
    

engine = create_engine('sqlite:///database/database.sqlite')  # Replace with your DB connection string
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = Flask(__name__)

# Configure upload folder (change path as needed)
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'research/uploads')
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx'}  # Allowed file extensions

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

def get_all_research():
    with get_db() as db:
        # Get all research objects from the table
        research_data = db.query(Research).all()
        # Convert research objects to a list of dictionaries
        research_list = []
        for research in research_data:
            # Customize the data to include relevant fields from Research object
            research_dict = {
                'id': research.id,
                'title': research.title,
                'abstract': research.abstract,
                'file_name': research.file_name,
                'summary': research.abstract[:200] + '...' if research.abstract else research.summary,
            }
            research_list.append(research_dict)

        return research_list

def get_all_feedback():
    with get_db() as db:
        # Get all feedback objects from the table
        feedback_data = db.query(Feedback).all()
        # Convert feedback objects to a list of dictionaries
        feedback_list = []
        for feedback in feedback_data:
            # Customize the data to include relevant fields from Feedback object
            feedback_dict = {
                'id': feedback.id,
                'question_asked': feedback.question_asked,
                'answer': feedback.answer,
                'bullet_points': feedback.bullet_points,
                'test_question': feedback.test_question,
            }
            feedback_list.append(feedback_dict)
        
        return feedback_list

def save_feedback_to_txt(feedback_data):
  """
  Saves the feedback response to a text file named "feedback.txt".

  Args:
      feedback_data (dict): The dictionary containing the feedback response information.
  """
  with open("research/feedback.txt", "w") as f:
    f.write(json.dumps(feedback_data))

  print("Feedback saved to feedback.txt")


@app.route('/research/<id>')
def view_research(id):
    with get_db() as db:
        research = db.query(Research).filter(Research.id == id).first()
        if research is None:
            return jsonify({'status': 'No research data found for '+id}), 404
        return jsonify(research.to_dict())

@app.route('/research')
def list_research():
    research_data = get_all_research()
    if research_data is None:
        return jsonify({'status': 'No research data found'}), 404
    return jsonify(research_data)

@app.route('/feedback')
def list_feedback():
    feedback_data = get_all_feedback()
    if feedback_data is None:
        return jsonify({'status': 'No feedback data found'}), 404
    return jsonify(feedback_data)

@app.route('/publish-doc', methods=['GET'])
def view_publish_doc():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'research_file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['research_file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(UPLOAD_FOLDER, filename))

        # Parse data based on file type
        if filename.endswith('txt'):
            import re
            with open(os.path.join(UPLOAD_FOLDER, filename), 'r') as f:
                lines = f.readlines()
                title = lines[0].strip()
                abstract ='\n'.join(lines[1:])
        elif filename.endswith(('pdf')):
            import PyPDF2
            with open(os.path.join(UPLOAD_FOLDER, filename), 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                title = pdf_reader.getDocumentInfo().title
                abstract = pdf_reader.getPage(1).extractText()
        else:
            title = None
            abstract = None

        # Create summary
        with open(os.path.join(UPLOAD_FOLDER, filename), 'r', encoding='utf-8') as f:
            file_contents = f.read()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You: Summarize the following document:"},
                {"role": "user", "content": file_contents}
            ],
            max_tokens=100,
            stop=None,
            temperature=0.5,
        )
        
        summary =  response.choices[0].message.content.strip()
        doc_id = str(uuid4())
        
        with get_db() as db:
            new_research = Research(id=doc_id, title=title, abstract=abstract, file_name=filename, summary=summary)
            db.add(new_research)
            db.commit()

        return jsonify({'message': 'File uploaded and summarized successfully', 'data': {'document_id': doc_id}}), 201
    else:
        return jsonify({'error': 'Unsupported file format'}), 400

@app.route('/query', methods = ['POST'])
def query():

    data = request.get_json()
    if not validate_request(data):
        return jsonify({'error': 'Missing required document or question'}), 400

    document_id = data['document_id']
    question = data['question']

    research_doc = get_research(document_id)
    if not research_doc:
        return jsonify({'error': f'No research found for {document_id}'}), 404

    try:
        response = ask_openai(research_doc, question)
        feedback = response.choices[0].message.content
        
        save_feedback_to_txt(feedback)
        
        with open(os.path.join('research/', 'feedback.txt'), 'r') as f:
            lines = f.readlines()
            answer = lines[0].strip()
            bullet_points ='\n'.join(lines[1:])
            question = '\n'.join(lines[2:])
            
        print(answer)
        print(bullet_points)
        print(question)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({
        'message': 'Question submitted successfully',
        'feedback': feedback
    })

def read_feedback_file():
    with open(os.path.join('research/', 'feedback.txt'), 'r') as f:
        lines = f.readlines()
        answer = lines[0].strip()
        bullet_points ='\n'.join(lines[1:])
        question = '\n'.join(lines[2:])
            
    print(answer)
    print("answer above")
    print(bullet_points)
    print("bullet points above")
    print(question)
    print("question above")

def validate_request(data):
    return data and data.get('document_id') and data.get('question')

def get_research(document_id):
    with get_db() as db:
        return db.query(Research).filter(Research.id == document_id).first()

def ask_openai(research_doc, question):
    # call OpenAI API
    return client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"You: {question} in this document, also when returning the response it is highly important for it to be in a valid json syntax `the answer to the question asked, A list of bullet points emphasizing key details in the answer to improve understanding, A generated question to evaluate if the user understood the answer provided`"},
                {"role": "user", "content": research_doc.abstract}
            ],
            max_tokens=300,
            stop=None,
            temperature=0.5,
        )

def save_feedback(id, question, feedback):
    with get_db() as db:
        db.add(Feedback(
            id=id, 
            question_asked=question,
            bullet_points=feedback['key_details'],
            test_question=feedback['question'],
            answer=feedback['answer']
        ))
        db.commit()

if __name__ == '__main__':
    app.run(debug=True)

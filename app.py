import streamlit as st
import requests
import smtplib
import ssl
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import speech_recognition as sr
import pyttsx3
from PyPDF2 import PdfReader
from docx import Document
from duckduckgo_search import DDGS

# ---------- Setup ----------
st.set_page_config(page_title="Ollama AI Chatbot", layout="centered")
engine = pyttsx3.init()
recognizer = sr.Recognizer()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "file_text" not in st.session_state:
    st.session_state.file_text = ""
if "last_input_type" not in st.session_state:
    st.session_state.last_input_type = "text"

# ---------- File Processing ----------
def extract_text(file):
    ext = file.name.split(".")[-1].lower()
    if ext == "pdf":
        reader = PdfReader(file)
        return "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
    elif ext == "docx":
        doc = Document(file)
        return "\n".join([p.text for p in doc.paragraphs])
    elif ext == "txt":
        return file.read().decode("utf-8")
    return ""

st.sidebar.header("📄 Upload File")
uploaded_file = st.sidebar.file_uploader("Choose PDF, DOCX, or TXT", type=["pdf", "docx", "txt"])

if uploaded_file:
    st.session_state.file_text = extract_text(uploaded_file)
    st.sidebar.success("✅ File uploaded.")

# ---------- Model Detection ----------
def detect_model(prompt):
    code_keywords = ["def ", "class ", "import ", "function", "{", "}", "html", "css", "<", ">"]
    return "deepseek-coder" if any(word in prompt.lower() for word in code_keywords) else "llama3"

# ---------- Call LLM ----------
def query_model(prompt):
    model = detect_model(prompt)
    try:
        res = requests.post("http://localhost:11434/api/generate", json={
            "model": model,
            "prompt": prompt,
            "stream": False
        })
        result = res.json()
        return result.get("response", "⚠️ No response received from the model."), model
    except Exception as e:
        return f"❌ Error: {str(e)}", model

# ---------- Audio to Text ----------
def transcribe_audio():
    with sr.Microphone() as source:
        audio = recognizer.listen(source)
        try:
            return recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            return f"Speech Recognition error: {e}"

# ---------- Text-to-Speech ----------
def speak(text):
    engine.say(text)
    engine.runAndWait()

# ---------- Email Automation ----------
def send_email_gmail(to_email, subject, body):
    email_address = st.secrets["email"]
    email_password = st.secrets["email_password"]

    message = MIMEMultipart()
    message["From"] = email_address
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(email_address, email_password)
            server.sendmail(email_address, to_email, message.as_string())
        return "✅ Email sent successfully!"
    except Exception as e:
        return f"❌ Failed to send email: {str(e)}"

# ---------- Web Search ----------
def web_search(query, max_results=3):
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append(f"🔗 [{r['title']}]({r['href']})\n{r['body']}")
    return "\n\n".join(results) if results else "⚠️ No results found."

# ---------- Task Detection ----------
def detect_task(user_input):
    email_pattern = r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)"
    if re.search(email_pattern, user_input) and any(word in user_input.lower() for word in ["email", "mail", "send"]):
        return "email"
    elif any(word in user_input.lower() for word in ["find", "look up", "search for", "what is", "who is", "tell me about"]):
        return "search"
    else:
        return "chat"

# ---------- Parse Email Prompt ----------
def parse_email(user_input):
    email_match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", user_input)
    if email_match:
        to_email = email_match.group(1)
        subject = "No Subject"
        body = user_input.split(to_email)[-1].strip()
        if "about" in body:
            parts = body.split("about")
            subject = parts[1].strip().split()[0]
            body = body.replace(f"about {subject}", "").strip()
        return to_email, subject, body
    return None, None, None

# ---------- UI ----------
st.markdown("<h2>AI-Powered Conversational Agent with OLLAMA( DeepSeek & LLaMA3)! 🤖</h2>", unsafe_allow_html=True)
col1, col2, col3 = st.columns([8, 1, 1])
with col1:
    user_input = st.text_input("Chat Input", placeholder="Type your message or use 🎙️...", label_visibility="collapsed")
with col2:
    if st.button("🎙️", help="Click to speak"):
        # Start listening and populate the text box with the transcribed text
        user_input = transcribe_audio()  # This updates the user_input with the transcribed text
        st.session_state.last_input_type = "voice"
        st.rerun()  # Re-run the script to update the text input field
with col3:
    send = st.button("➡️")

# ---------- Handle Submission ----------
if user_input and send:
    st.session_state.messages.append({"role": "user", "content": user_input})

    task = detect_task(user_input)
    if task == "email":
        to_email, subject, body = parse_email(user_input)
        if to_email:
            reply = send_email_gmail(to_email, subject, body)
        else:
            reply = "❌ Could not parse email address."
    elif task == "search":
        reply = web_search(user_input)
    else:
        full_prompt = user_input
        if st.session_state.file_text:
            full_prompt = f"Answer based on this file:\n{st.session_state.file_text[:1500]}\n\nQuestion: {user_input}"
        reply, model_used = query_model(full_prompt)

    st.session_state.messages.append({"role": "assistant", "content": reply})

    if st.session_state.last_input_type == "voice":
        speak(reply)
    st.session_state.last_input_type = "text"

# ---------- Chat Display ----------
st.markdown("<hr>", unsafe_allow_html=True)
for msg in st.session_state.messages:
    role = "You" if msg["role"] == "user" else "Agent"
    if msg["role"] == "user":
        st.markdown(f"**{role}🗣️**: {msg['content']}", unsafe_allow_html=True)
    else:
        st.markdown(f"**{role}🤖**: {msg['content']}", unsafe_allow_html=True)
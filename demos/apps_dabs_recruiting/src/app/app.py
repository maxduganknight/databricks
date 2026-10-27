"""
Recruiter Chatbot — Databricks Apps Demo

AI-powered assistant that helps recruiters match candidates to job opportunities.
Uses the Databricks Foundation Model API (via OpenAI-compatible endpoint) so all
inference stays within the Databricks workspace — no external API calls.
"""

import os

import streamlit as st
from databricks.sdk import WorkspaceClient
from openai import OpenAI

# --- Databricks Foundation Model API setup ---
w = WorkspaceClient()


def get_api_key():
    """Get OAuth token from the SDK — works in Apps runtime (service principal)."""
    headers = w.config.authenticate()
    return headers.get("Authorization", "").replace("Bearer ", "")


client = OpenAI(
    api_key=get_api_key(),
    base_url=f"{w.config.host}/serving-endpoints",
)

MODEL = os.getenv("CHAT_MODEL", "databricks-claude-sonnet-4")

SYSTEM_PROMPT = """You are an AI recruiting assistant for a career wellness platform.
You help recruiters match candidates to job opportunities based on skills, experience,
and career goals. You also help draft outreach messages, summarize candidate profiles,
and suggest interview questions.

When matching candidates to jobs, consider:
- Skills alignment (hard skills and soft skills)
- Experience level and career trajectory
- Geographic preferences and remote work availability
- Industry fit and career transition potential
- Salary range compatibility

Be concise, professional, and empathetic. Remember that career transitions are personal
and candidates deserve respectful, thoughtful matching.

If asked about data handling: all processing stays within the Databricks workspace.
No candidate PII is sent to external services."""

# --- Streamlit UI ---
st.set_page_config(
    page_title="Recruiter Assistant",
    page_icon=":briefcase:",
    layout="wide",
)

st.title(":briefcase: Recruiter Assistant")
st.caption(
    "AI-powered candidate-job matching | Powered by Databricks Foundation Model API"
)

# Sidebar with sample prompts
with st.sidebar:
    st.header("Quick Actions")
    sample_prompts = [
        "Match this candidate to open roles: 5 years Python, data engineering, "
        "wants remote work in Canada, currently $110K",
        "Draft an outreach message for a senior data scientist interested in career "
        "wellness / HR tech",
        "Suggest interview questions for a data engineer transitioning from finance "
        "to health tech",
        "Summarize this candidate profile: 3 years as a full-stack developer, "
        "React and Node.js, bootcamp grad, looking to move into AI/ML",
    ]
    for prompt in sample_prompts:
        if st.button(prompt[:60] + "...", key=prompt):
            st.session_state["prefill"] = prompt

    st.divider()
    st.markdown("**Model:** " + MODEL)

# Chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Handle prefilled prompt from sidebar
prefill = st.session_state.pop("prefill", None)
user_input = st.chat_input(
    "Ask about candidate matching, outreach, or interview prep..."
)

if prefill:
    user_input = prefill

if user_input:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Build message list for API call
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Keep last 10 turns for context
    for msg in st.session_state.messages[-10:]:
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    # Stream response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=api_messages,
                    max_tokens=1024,
                    temperature=0.7,
                )
                reply = response.choices[0].message.content
                st.markdown(reply)
                st.session_state.messages.append(
                    {"role": "assistant", "content": reply}
                )
            except Exception as e:
                st.error(f"Error calling model: {e}")

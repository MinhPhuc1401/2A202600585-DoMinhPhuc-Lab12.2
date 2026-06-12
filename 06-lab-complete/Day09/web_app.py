from __future__ import annotations

import sys
from pathlib import Path
import json

# Add src/ to sys.path to resolve imports correctly
sys.path.append(str(Path(__file__).resolve().parent / "src"))

import streamlit as st
from app.graph import ShoppingAssistant

# Set Streamlit Page Config
st.set_page_config(
    page_title="Multi-Agent Shopping Assistant",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium Styling
st.markdown("""
<style>
    /* App Title Styling */
    .app-title {
        font-family: 'Outfit', 'Inter', sans-serif;
        font-weight: 800;
        font-size: 2.8rem;
        background: linear-gradient(135deg, #FF6B6B 0%, #4D96FF 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    
    /* Subtle Glassmorphism Card for Final Answer */
    .answer-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 1.5rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
        margin-top: 1rem;
        margin-bottom: 1.5rem;
    }
    
    /* Header labels styling */
    .section-header {
        font-family: 'Outfit', sans-serif;
        font-weight: 600;
        font-size: 1.5rem;
        color: #4D96FF;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


# Initialize ShoppingAssistant in session state to avoid reload on rerun
@st.cache_resource
def get_assistant():
    return ShoppingAssistant()

try:
    assistant = get_assistant()
except Exception as e:
    st.error(f"Lỗi khởi tạo ShoppingAssistant: {e}")
    st.info("Vui lòng kiểm tra lại cấu hình API Key và biến môi trường trong file `.env`.")
    st.stop()


# Load sample questions from data/test.json
test_file = Path(__file__).resolve().parent / "data" / "test.json"
sample_questions = []
if test_file.exists():
    try:
        with open(test_file, "r", encoding="utf-8") as f:
            test_cases = json.load(f)
            for case in test_cases:
                sample_questions.append({
                    "label": f"[{case.get('id')}] - {case.get('question')[:60]}...",
                    "question": case.get("question"),
                    "id": case.get("id")
                })
    except Exception as e:
        st.sidebar.warning(f"Không thể đọc file câu hỏi mẫu: {e}")


# SIDEBAR SETUP
st.sidebar.markdown("<h2 style='text-align: center; color: #FF6B6B;'>🛍️ VinShop Demo</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")

st.sidebar.subheader("Câu hỏi kiểm thử mẫu")
selected_sample = st.sidebar.selectbox(
    "Chọn câu hỏi từ bộ test.json:",
    options=["Nhập câu hỏi tự do..."] + [q["label"] for q in sample_questions]
)

# Map selected question
default_question_value = ""
if selected_sample != "Nhập câu hỏi tự do...":
    idx = [q["label"] for q in sample_questions].index(selected_sample)
    default_question_value = sample_questions[idx]["question"]

st.sidebar.markdown("---")
st.sidebar.subheader("Quản lý Chỉ mục RAG")
rebuild_clicked = st.sidebar.button("Rebuild Chroma Index")
if rebuild_clicked:
    with st.sidebar.spinner("Đang xây dựng lại Chroma Index..."):
        try:
            assistant.policy_store.rebuild(assistant.settings.policy_path)
            st.sidebar.success("Xây dựng lại Chroma Index thành công!")
        except Exception as e:
            st.sidebar.error(f"Lỗi rebuild index: {e}")

st.sidebar.markdown("---")
st.sidebar.markdown(f"**LLM Model:** `{assistant.settings.model}`")
st.sidebar.markdown(f"**Embedding Model:** `all-MiniLM-L6-v2`")
st.sidebar.markdown(f"**Total policy chunks:** `{assistant.policy_store.collection.count()}`")


# MAIN AREA SETUP
st.markdown("<h1 class='app-title'>Multi-Agent Shopping Assistant</h1>", unsafe_allow_html=True)
st.markdown("<p style='font-style: italic; color: #888;'>Giao diện Web trực quan hóa luồng chạy Multi-Agent sử dụng LangGraph & Chroma DB</p>", unsafe_allow_html=True)

# Query Input Form
with st.form("query_form"):
    user_query = st.text_area(
        "Nhập câu hỏi của bạn:",
        value=default_question_value,
        placeholder="Nhập câu hỏi của bạn tại đây...",
        height=70
    )
    submit_button = st.form_submit_button("Gửi câu hỏi")

if submit_button and user_query:
    with st.spinner("Hệ thống Multi-Agent đang xử lý câu hỏi của bạn..."):
        try:
            # Execute ask
            result = assistant.ask(user_query)
            
            # Display final answer
            st.markdown("<div class='section-header'>💬 Phản hồi </div>", unsafe_allow_html=True)
            
            raw_answer = result.get('final_answer', '')
            clean_answer = raw_answer
            
            import re
            # Parse Success format: "Answer: ... \nEvidence: ..."
            if re.search(r'^\s*Answer\s*:', clean_answer, re.IGNORECASE):
                parts = re.split(r'\bEvidence\s*:', clean_answer, flags=re.IGNORECASE)
                if parts:
                    clean_answer = parts[0].strip()
                clean_answer = re.sub(r'^\s*Answer\s*:\s*', '', clean_answer, flags=re.IGNORECASE)
            # Parse Clarification format: "Status: clarification_needed \nQuestion: ..."
            elif re.search(r'Status\s*:\s*clarification_needed', clean_answer, re.IGNORECASE):
                q_match = re.search(r'Question\s*:\s*(.*)', clean_answer, re.IGNORECASE | re.DOTALL)
                if q_match:
                    clean_answer = q_match.group(1).strip()
            # Parse Not found format: "Status: not_found \nMessage: ..."
            elif re.search(r'Status\s*:\s*not_found', clean_answer, re.IGNORECASE):
                m_match = re.search(r'Message\s*:\s*(.*)', clean_answer, re.IGNORECASE | re.DOTALL)
                if m_match:
                    clean_answer = m_match.group(1).strip()
                    
            st.markdown(f"<div class='answer-card'>{clean_answer}</div>", unsafe_allow_html=True)
            
            # Visual Execution Path (Timeline / Trace representation)
            st.markdown("<div class='section-header'>🧬 Luồng thực thi của các Agent (Execution Trace)</div>", unsafe_allow_html=True)
            
            # Draw st.status or st.chat_message for each step
            for idx, step in enumerate(result.get("trace", [])):
                node_name = step.get("node")
                
                if node_name == "supervisor":
                    with st.expander(f"📍 Bước {idx+1}: Supervisor Node", expanded=True):
                        st.markdown("**Nhiệm vụ:** Phân tích câu hỏi và điều phối luồng xử lý.")
                        output = step.get("output", {})
                        st.write(f"- Trạng thái: `{output.get('status')}`")
                        st.write(f"- Cần Chính sách (Policy): `{output.get('needs_policy')}`")
                        st.write(f"- Cần Dữ liệu (Data): `{output.get('needs_data')}`")
                        if output.get("clarification_question"):
                            st.info(f"Yêu cầu làm rõ: {output.get('clarification_question')}")
                        st.json(output)
                        
                elif node_name == "worker_1_policy":
                    with st.expander(f"📍 Bước {idx+1}: Policy Worker Node (Worker 1)", expanded=True):
                        st.markdown("**Nhiệm vụ:** Tìm kiếm RAG trên file Markdown chính sách mua sắm.")
                        res = step.get("policy_result", {})
                        st.markdown(f"**Tóm tắt chính sách:** {res.get('summary')}")
                        
                        # Show tool calls
                        st.subheader("Cuộc gọi RAG Tool:")
                        tool_calls = step.get("tool_calls", [])
                        for tc in tool_calls:
                            st.write(f"🔧 Tool: `{tc['tool_name']}`")
                            st.write(f"📥 Arguments: `{tc['arguments']}`")
                            # Format retrieved chunks
                            try:
                                chunks = json.loads(tc["output"])
                                st.write(f"📚 Tìm thấy {len(chunks)} chunks liên quan:")
                                for c_idx, chunk in enumerate(chunks):
                                    st.markdown(f"**Chunk {c_idx+1}:** *{chunk['citation']}* (Distance: `{chunk['distance']:.4f}`)")
                                    st.text(chunk["content"][:300] + "...")
                            except:
                                st.text(str(tc["output"]))
                        st.json(res)
                        
                elif node_name == "worker_2_data":
                    with st.expander(f"📍 Bước {idx+1}: Data Lookup Worker Node (Worker 2)", expanded=True):
                        st.markdown("**Nhiệm vụ:** Tra cứu dữ liệu khách hàng, đơn hàng, hoặc voucher từ database mock.")
                        res = step.get("data_result", {})
                        st.markdown(f"**Tóm tắt dữ liệu:** {res.get('summary')}")
                        
                        # Show tool calls
                        st.subheader("Cuộc gọi Data Lookup Tools:")
                        tool_calls = step.get("tool_calls", [])
                        if not tool_calls:
                            st.write("Không gọi tool nào.")
                        for tc in tool_calls:
                            st.write(f"🔧 Tool: `{tc['tool_name']}`")
                            st.write(f"📥 Arguments: `{tc['arguments']}`")
                            try:
                                out_data = json.loads(tc["output"])
                                st.json(out_data)
                            except:
                                st.text(str(tc["output"]))
                        st.json(res)
                        
                elif node_name == "worker_3_response":
                    with st.expander(f"📍 Bước {idx+1}: Response Synthesizer Node (Worker 3)", expanded=True):
                        st.markdown("**Nhiệm vụ:** Hợp nhất các thông tin và trả về kết quả chuẩn định dạng.")
                        st.text(step.get("final_answer"))
                        
        except Exception as e:
            st.error(f"Lỗi trong quá trình chạy Multi-Agent: {e}")
            import traceback
            st.text(traceback.format_exc())

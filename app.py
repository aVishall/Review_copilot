import streamlit as st
import os
import requests
from datetime import datetime
import re
import json
import zipfile
import io
from content_validator import (
    validate_mcq,
    find_relevant_content,
    check_grammar,
    check_complexity,
    validate_code_output,
    check_learning_outcome,
    validate_test_cases
)
import openai
import subprocess
from PIL import Image  # Import PIL for image handling
import matplotlib.pyplot as plt
import sqlite3
import PyPDF2  # Importing PyPDF2 for PDF handling

def set_openai_api_key():
    """Set the OpenAI API key for Azure OpenAI."""
    openai.api_type = "azure"
    openai.api_base = "https://nw-tech-dev.openai.azure.com"
    openai.api_version = "2023-03-15-preview"
    openai.api_key = "aa4f2f35c7634fcb8f5b652bbfb36926"

def validate_html_css(html_code, css_code, test_case):
    results = []
    
    if test_case['testcase_evaluation_type'] == 'CLIENT_SIDE_EVALUATION':
        # Create a temporary HTML file with both HTML and CSS
        soup = BeautifulSoup(html_code, 'html.parser')
        
        # Add CSS to the head
        style_tag = soup.new_tag('style')
        style_tag.string = css_code
        if soup.head:
            soup.head.append(style_tag)
        else:
            head = soup.new_tag('head')
            head.append(style_tag)
            soup.html.insert(0, head)
            
        # For client-side evaluation, we'll do basic checks
        if 'display: grid' in css_code.lower():
            results.append(True)
        else:
            results.append(False)
            
    elif test_case['testcase_evaluation_type'] == 'CSS_PARSER':
        # Handle CSS specific tests
        if 'grid-template-columns' in test_case['display_text']:
            pattern = r'grid-template-columns:\s*repeat\(2,\s*350px\)'
            results.append(bool(re.search(pattern, css_code, re.IGNORECASE)))
            
        elif 'grid-template-rows' in test_case['display_text']:
            pattern = r'grid-template-rows:\s*repeat\(2,\s*300px\)'
            results.append(bool(re.search(pattern, css_code, re.IGNORECASE)))
            
    return all(results)

def login_and_get_cheatsheets(url, mobile, otp):
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    
    try:
        st.info("Starting login process...")
        
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 20)
        
        try:
            # Load the page
            driver.get(url)
            st.info("Page loaded, waiting for elements...")
            
            # Wait for phone input to be present and visible
            phone_field = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[inputmode='numeric']"))
            )
            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[inputmode='numeric']")))
            
            # Clear and enter phone number using JavaScript
            driver.execute_script("""
                let input = document.querySelector("input[inputmode='numeric']");
                input.value = arguments[0];
                input.dispatchEvent(new Event('input', { bubbles: true }));
            """, mobile)
            
            st.info("Entered phone number, waiting for OTP button...")
            
            # Wait for and click OTP button
            otp_button = wait.until(
                EC.element_to_be_clickable((By.ID, "getOTPButton"))
            )
            driver.execute_script("arguments[0].click();", otp_button)
            
            st.info("Clicked OTP button, waiting for OTP field...")
            
            # Wait for OTP input field
            otp_field = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'][pattern='[0-9]*']"))
            )
            
            # Enter OTP using JavaScript
            driver.execute_script("""
                let input = document.querySelector("input[type='text'][pattern='[0-9]*']");
                input.value = arguments[0];
                input.dispatchEvent(new Event('input', { bubbles: true }));
            """, otp)
            
            st.info("Entered OTP, waiting for verification...")
            
            # Wait for redirect or success indicator
            wait.until(
                lambda driver: driver.current_url != url
            )
            
            st.success("Login successful!")
            
            # Navigate to cheatsheets page
            driver.get("https://learning-beta.earlywave.in/cheatsheets")
            
            # Get page content
            content = driver.page_source
            return content
            
        except Exception as e:
            st.error(f"Error during login process: {str(e)}")
            st.error("Page source:")
            st.code(driver.page_source)
            return None
            
    except Exception as e:
        st.error(f"Failed to initialize browser: {str(e)}")
        return None
        
    finally:
        try:
            if 'driver' in locals():
                driver.quit()
        except:
            pass

def display_question(question_data, is_review_mode=False):
    # Display question details
    st.subheader("Question Details")
    st.markdown(question_data.get('question_text', 'N/A'))
    
    # Get default code
    default_code = question_data.get('default_code_metadata', [])
    html_code = next((item['code_data'] for item in default_code if item['language'] == 'HTML'), '')
    css_code = next((item['code_data'] for item in default_code if item['language'] == 'CSS'), '')
    
    # Code editors
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("HTML Code")
        html_input = st.text_area("HTML", value=html_code, height=300, key=f"html_{question_data.get('question_id', '')}")
    
    with col2:
        st.subheader("CSS Code")
        css_input = st.text_area("CSS", value=css_code, height=300, key=f"css_{question_data.get('question_id', '')}")
    
    if st.button("Run Tests", key=f"button_{question_data.get('question_id', '')}"):
        st.subheader("Test Results")
        for test_case in question_data.get('test_cases', []):
            result = validate_html_css(html_input, css_input, test_case)
            status = "✅ PASSED" if result else "❌ FAILED"
            st.write(f"{status} - {test_case['display_text']}")
            if not result:
                st.write(f"Weightage: {test_case['weightage']}")
            st.write("---")
    
    # If in review mode, show additional review options
    if is_review_mode and 'cheatsheet_content' in st.session_state:
        display_review_report(question_data, st.session_state.cheatsheet_content)

def display_review_report(question_data, cheatsheet_content):
    st.subheader("Review Report")
    
    # Question Description Review
    st.write("### I. Question Description Review")
    description_issues = validate_question_description(question_data, cheatsheet_content)
    if description_issues:
        for issue in description_issues:
            st.warning(issue)
    else:
        st.success("Question description appears to be clear and consistent")
    
    # Solution Review
    st.write("### II. Solution Review")
    solution_issues = validate_solution(question_data)
    if solution_issues:
        for issue in solution_issues:
            st.warning(issue)
    else:
        st.success("Solution code appears to be properly formatted")
    
    # Test Cases Review
    st.write("### III. Test Cases Review")
    for test_case in question_data.get('test_cases', []):
        st.write(f"**Test Case:** {test_case['display_text']}")
        
        # Get solution code
        solution = next((item['code_details'] for item in question_data.get('solutions_metadata', [{}]) 
                        if item.get('order') == 1), [])
        html_code = next((item['code_data'] for item in solution if item['language'] == 'HTML'), '')
        css_code = next((item['code_data'] for item in solution if item['language'] == 'CSS'), '')
        
        # Run test variations
        test_results = test_case_validation(html_code, css_code, test_case)
        
        # Display results
        for result in test_results:
            status = "✅ PASSED" if result['passed'] else "❌ FAILED"
            st.write(f"{status} - {result['type']}")
            if not result['passed']:
                st.code(result['input'])
        st.write("---")

def store_cheat_sheet(content):
    """Store the cheat sheet content in the database."""
    conn = sqlite3.connect('cheat_sheets.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO cheat_sheets (content) VALUES (?)', (content,))
    conn.commit()
    conn.close()

def fetch_cheat_sheets():
    """Fetch all cheat sheets from the database."""
    conn = sqlite3.connect('cheat_sheets.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM cheat_sheets')
    rows = cursor.fetchall()
    conn.close()
    return rows

def process_uploaded_file(uploaded_file):
    """Process the uploaded file based on its type."""
    if uploaded_file.type == "application/pdf":
        # Read PDF file
        reader = PyPDF2.PdfReader(uploaded_file)
        content = ""
        for page in reader.pages:
            content += page.extract_text() + "\n"
        return content
    elif uploaded_file.type in ["text/plain", "text/markdown"]:
        # Read text or markdown file
        return uploaded_file.read().decode("utf-8")
    elif uploaded_file.type == "application/json":
        # Read JSON file
        cheat_sheet_data = json.load(uploaded_file)
        return json.dumps(cheat_sheet_data, indent=2)  # Convert JSON to string
    else:
        st.warning("Unsupported file type. Please upload PDF, MD, TXT, or JSON files.")
        return None

def main():
    st.title("NxtReview")
    
    # Initialize session state for selected question if not exists
    if 'selected_question' not in st.session_state:
        st.session_state.selected_question = 0
    
    # Main menu with updated "Cheat Sheet" option
    menu = st.sidebar.selectbox(
        "Select Section",
        ["Home", "Cheat Sheet", "MCQs", "Coding Questions"]
    )
    
    if menu == "Home":
        st.write("Welcome to the Review Copilot!")
        st.write("Please select a section from the sidebar.")
        
    elif menu == "Cheat Sheet":
        st.header("Cheat Sheet Content")
        
        # File uploader for cheat sheet content
        uploaded_file = st.file_uploader("Upload Cheat Sheet File", type=['txt', 'json', 'md'], key="cheat_sheet_upload")
        
        if uploaded_file:
            # Extract and display cheat sheet content
            if uploaded_file.type == "application/json":
                cheat_sheet_data = json.load(uploaded_file)
                st.write("### Cheat Sheet Content (JSON):")
                st.json(cheat_sheet_data)  # Display JSON content nicely
            else:
                cheat_sheet_content = uploaded_file.read().decode("utf-8")
                st.write("### Cheat Sheet Content:")
                st.markdown(cheat_sheet_content)  # Display text or markdown content

    elif menu == "MCQs":
        show_mcq_review_section()
        
    elif menu == "Coding Questions":
        st.header("Coding Questions")
        uploaded_file = st.file_uploader("Upload Question JSON", type=['json'], key="coding_upload")
        
        if uploaded_file:
            process_questions(uploaded_file, is_review_mode=False)

def process_questions(uploaded_file, is_review_mode=False):
    # Load the JSON data
    json_data = json.load(uploaded_file)
    
    # Handle both list and single question formats
    questions = json_data if isinstance(json_data, list) else [json_data]
    
    # Create a selection box for questions
    question_titles = [q.get('short_text', f"Question {i+1}") for i, q in enumerate(questions)]
    selected_question = st.selectbox(
        "Select Question to Review",
        range(len(questions)),
        format_func=lambda x: question_titles[x],
        key="question_selector"
    )
    
    # Display selected question
    st.markdown("---")
    display_question(questions[selected_question], is_review_mode)
    
    # Display question navigation
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if selected_question > 0:
            if st.button("← Previous Question"):
                st.session_state.selected_question = selected_question - 1
                st.rerun()
    with col2:
        if selected_question < len(questions) - 1:
            if st.button("Next Question →"):
                st.session_state.selected_question = selected_question + 1
                st.rerun()

def show_mcq_review_section():
    st.header("MCQ Review Platform")
    
    uploaded_zip = st.file_uploader("Upload Question JSONs", type=['zip'])
    
    if uploaded_zip:
        try:
            with zipfile.ZipFile(uploaded_zip) as zip_file:
                file_list = zip_file.namelist()
                
                # Group files by question type
                question_files = {
                    'default_new': [],
                    'code_analysis': [],
                    'fib_html': []  # Ensure this is included for FIB HTML questions
                }
                
                # Categorize files
                for file in file_list:
                    try:
                        # Log the file being processed
                        st.write(f"Processing file: {file}")
                        
                        # Check if the file is in the FIB_HTML_CODING folder and is a JSON file
                        if 'FIB_HTML_CODING/' in file and file.endswith('.json'):
                            with zip_file.open(file) as json_file:
                                data = json.load(json_file)
                                
                                # Ensure data is a list
                                if isinstance(data, list):
                                    for q in data:
                                        if isinstance(q, dict):  # Ensure each question is a dictionary
                                            q_type = q.get('question_type', '')
                                            content_type = q.get('content_type', '')

                                            if q_type == 'FIB_HTML_CODING' and content_type == 'MARKDOWN':
                                                # Extract required fields for FIB HTML questions
                                                question_id = q.get('question_id', '')
                                                question_text = q.get('question_text', '')
                                                tag_names = q.get('tag_names', [])
                                                
                                                # Extract initial code from fib_html_coding
                                                initial_code = ""
                                                if 'fib_html_coding' in q:
                                                    for code_block in q['fib_html_coding']:
                                                        if isinstance(code_block, dict):  # Ensure it's a dictionary
                                                            for block in code_block.get('code_blocks', []):
                                                                initial_code += block.get('code', '') + "\n"
                                                
                                                # Extract solution code
                                                solution_code = ""
                                                if 'solution' in q:
                                                    for solution in q['solution']:
                                                        if isinstance(solution, dict):  # Ensure it's a dictionary
                                                            for block in solution.get('code_blocks', []):
                                                                solution_code += block.get('code', '') + "\n"
                                                
                                                # Append extracted data to the fib_html list
                                                question_files['fib_html'].append({
                                                    'question_id': question_id,
                                                    'question_text': question_text,
                                                    'tag_names': tag_names,
                                                    'initial_code': initial_code.strip(),
                                                    'solution_code': solution_code.strip()
                                                })
                                else:
                                    st.warning(f"Expected a list of questions in file {file}, but got: {type(data)}")
                        elif file.endswith('.json'):  # Process other JSON files outside FIB_HTML_CODING
                            with zip_file.open(file) as json_file:
                                data = json.load(json_file)
                                questions = data if isinstance(data, list) else [data]
                                
                                for q in questions:
                                    q_type = q.get('question_type', '')
                                    if q_type == 'MULTIPLE_CHOICE':
                                        question_files['default_new'].append((file, q))
                                    elif q_type == 'CODE_ANALYSIS_MULTIPLE_CHOICE':
                                        question_files['code_analysis'].append((file, q))
                    except Exception as e:
                        st.error(f"Error processing file {file}: {str(e)}")
                
                # Create tabs for different question types
                tab1, tab2, tab3 = st.tabs([
                    "Default MCQs", 
                    "Code Analysis MCQs",
                    "FIB HTML Coding"
                ])
                
                with tab1:
                    review_default_mcqs(question_files['default_new'])
                    
                with tab2:
                    review_code_analysis_mcqs(question_files['code_analysis'])
                    
                with tab3:
                    review_fib_html_questions()
                    
        except Exception as e:
            st.error(f"Error processing ZIP: {str(e)}")

def review_default_mcqs(questions):
    if not questions:
        st.info("No Default MCQ questions found")
        return
        
    # Display total question count
    st.info(f"Total Default MCQ Questions: {len(questions)}")
    
    # Initialize session state for index if not exists
    if 'default_mcq_index' not in st.session_state:
        st.session_state.default_mcq_index = 0
    
    # Create dropdown with formatted question number and ID
    question_options = [f'Question {str(i+1).zfill(2)}: {q[1].get("question_id", "N/A")}' 
                       for i, q in enumerate(questions)]
    
    selected_index = st.selectbox(
        "Select Question",
        range(len(questions)),
        format_func=lambda x: question_options[x],
        key="default_mcq_selector",
        index=st.session_state.default_mcq_index
    )
    
    # Update session state when dropdown changes
    st.session_state.default_mcq_index = selected_index
    
    _, question = questions[selected_index]
    
    # Extract required fields
    question_id = question.get('question_id', 'N/A')
    question_content = question.get('question', {}).get('content', '')
    options = question.get('options', [])
    question_key = question.get('question_key', '')
    
    st.subheader(f"Question ID: {question_id}")
    
    with st.expander("Question Details", expanded=True):
        st.write("**Question:**", question_content)
        st.write("**Options:**")
        for opt in options:
            status = "✅" if opt.get('is_correct') else "❌"
            st.write(f"{status} {opt.get('content', '')}")
    
    with st.expander("Review Results", expanded=True):
        review_results = ai_review_default_mcq(question_content, options, question_key)
        
        for category, result in review_results.items():
            if result['status']:
                st.success(f"✅ {category}: {result['message']}")
            else:
                st.warning(f"⚠️ {category}: {result['message']}")
    
    # Navigation buttons in columns
    col1, col2, col3 = st.columns([1, 4, 1])
    
    with col1:
        if st.button("← Previous", key="prev_default"):
            if st.session_state.default_mcq_index > 0:
                st.session_state.default_mcq_index -= 1
                st.rerun()
    
    with col2:
        st.write(f"Question {selected_index + 1} of {len(questions)}")
    
    with col3:
        if st.button("Next →", key="next_default"):
            if st.session_state.default_mcq_index < len(questions) - 1:
                st.session_state.default_mcq_index += 1
                st.rerun()

def check_grammar_with_gpt(text):
    """Check grammar using GPT."""
    set_openai_api_key()  # Set the API key
    try:
        prompt = f"""
        Please check the following text for grammar issues and provide corrections if necessary:
        
        Text: {text}
        
        If there are any grammar issues, list them and provide the corrected version. If there are no issues, respond with 'No issues found.'
        """
        
        response = openai.ChatCompletion.create(
            engine="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a grammar expert."},
                {"role": "user", "content": prompt}
            ]
        )
        
        result = response['choices'][0]['message']['content']
        if "no issues found" in result.lower():
            return True, "No grammar issues found."
        else:
            return False, result
    except Exception as e:
        return False, f"Error checking grammar: {str(e)}"

def verify_learning_outcome(question_key, question_content):
    """Verify if the learning outcome is achieved using ChatGPT"""
    set_openai_api_key()  # Set the API key
    try:
        prompt = f"""
        As a learning expert, verify if the following learning outcome is achieved based on the question content:
        
        Learning Outcome: {question_key}
        Question Content: {question_content}
        
        Please provide a brief explanation if the learning outcome is not achieved.
        """
        
        response = openai.ChatCompletion.create(
            engine="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a learning expert."},
                {"role": "user", "content": prompt}
            ]
        )
        
        return response['choices'][0]['message']['content']
    except Exception as e:
        return f"Error verifying learning outcome: {str(e)}"

def verify_answer_with_gpt(question_text, code_data, correct_answer):
    """Verify if the provided answer is correct using GPT"""
    prompt = f"""
    Question: {question_text}
    Code: {code_data}
    Given Answer: {correct_answer}
    
    Please evaluate the correctness of the given answer based on the question and code. 
    If the answer is incorrect, explain why. If it is correct, confirm that it is correct.
    """
    
    response = openai.ChatCompletion.create(
        engine="gpt-4o",  # Use your specific engine
        messages=[
            {"role": "system", "content": "You are a technical expert."},
            {"role": "user", "content": prompt}
        ]
    )
    
    return response['choices'][0]['message']['content']

def ai_review_default_mcq(question_content, options, question_key):
    """AI-based review for default MCQs"""
    results = {
        'Grammar': {'status': True, 'message': 'No grammar issues found'},
        'Learning Outcome': {'status': True, 'message': 'Learning outcome is achieved'},
        'Technical Accuracy': {'status': True, 'message': 'Answer appears technically accurate'},
        'Cheat Sheet Relevance': {'status': True, 'message': 'MCQ is relevant to the cheat sheet.'}
    }
    
    # Check grammar using GPT
    grammar_status, grammar_message = check_grammar_with_gpt(question_content)
    results['Grammar']['status'] = grammar_status
    results['Grammar']['message'] = grammar_message
    
    # Verify learning outcome
    learning_outcome_message = verify_learning_outcome(question_key, question_content)
    if "not achieved" in learning_outcome_message.lower():
        results['Learning Outcome'] = {
            'status': False,
            'message': learning_outcome_message
        }
    
    # Get correct and wrong answers
    correct_answer = next((opt['content'] for opt in options if opt.get('is_correct')), None)
    wrong_answers = [opt['content'] for opt in options if not opt.get('is_correct')]
    
    # Verify technical accuracy with GPT
    if correct_answer and question_content:
        gpt_verification = verify_answer_with_gpt(
            question_content,
            question_content,
            correct_answer
        )
        
        # If GPT indicates the answer might be wrong
        if any(phrase in gpt_verification.lower() for phrase in ['incorrect', 'wrong', 'should be', 'actual answer']):
            results['Technical Accuracy'] = {
                'status': False,
                'message': f"GPT Analysis: {gpt_verification}"
            }
        else:
            results['Technical Accuracy'] = {
                'status': True,
                'message': f"GPT Verified: {gpt_verification}"
            }
    
    return results

def review_code_analysis_mcqs(questions):
    if not questions:
        st.info("No Code Analysis MCQ questions found")
        return
        
    # Display total question count
    st.info(f"Total Code Analysis Questions: {len(questions)}")
    
    # Initialize session state for index if not exists
    if 'code_analysis_index' not in st.session_state:
        st.session_state.code_analysis_index = 0
    
    # Create dropdown with formatted question number and ID
    question_options = []
    for i, (_, q) in enumerate(questions):
        input_output = q.get('input_output', [])
        question_id = input_output[0].get('question_id', 'N/A') if input_output else 'N/A'
        question_options.append(f'Question {i+1}: {question_id}')
    
    selected_index = st.selectbox(
        "Select Question",
        range(len(questions)),
        format_func=lambda x: question_options[x],
        key="code_analysis_selector",
        index=st.session_state.code_analysis_index
    )
    
    # Update session state when dropdown changes
    st.session_state.code_analysis_index = selected_index
    
    _, question = questions[selected_index]
    
    # Extract required fields
    input_output = question.get('input_output', [{}])[0]
    question_id = input_output.get('question_id', 'N/A')
    question_text = question.get('question_text', '')
    code_data = next((item.get('code_data', '') for item in question.get('code_metadata', []) 
                     if item.get('language') == 'HTML'), '')
    wrong_answers = input_output.get('wrong_answers', [])
    correct_answer = (input_output.get('output', []) or [''])[0]
    
    # Display question details
    st.subheader(f"Question ID: {question_id}")
    
    with st.expander("Question Details", expanded=True):
        st.write("**Question:**", question_text)
        if code_data:
            st.write("**Code:**")
            st.code(code_data, language='html')
        st.write("**Options:**")
        st.write("✅ Correct Answer:", correct_answer)
        st.write("❌ Wrong Answers:")
        for ans in wrong_answers:
            st.write(f"- {ans}")
    
    with st.expander("Review Results", expanded=True):
        review_results = ai_review_code_analysis(question_text, code_data, correct_answer, wrong_answers)
        
        for category, result in review_results.items():
            if result['status']:
                st.success(f"✅ {category}: {result['message']}")
            else:
                st.warning(f"⚠️ {category}: {result['message']}")
    
    # Navigation buttons with st.rerun() instead of st.experimental_rerun()
    col1, col2, col3 = st.columns([1, 4, 1])
    
    with col1:
        if st.button("← Previous", key="prev_code"):
            if st.session_state.code_analysis_index > 0:
                st.session_state.code_analysis_index -= 1
                st.rerun()
    
    with col2:
        st.write(f"Question {selected_index + 1} of {len(questions)}")
    
    with col3:
        if st.button("Next →", key="next_code"):
            if st.session_state.code_analysis_index < len(questions) - 1:
                st.session_state.code_analysis_index += 1
                st.rerun()

def verify_code_relevance(question_text, code):
    """Check if the code is relevant to the question using GPT"""
    set_openai_api_key()  # Set the API key
    try:
        prompt = f"""
        Please analyze the following question and code to determine if the code is relevant to answering the question:
        
        Question: {question_text}
        Code: {code}
        
        Provide a brief explanation of your analysis.
        """
        
        response = openai.ChatCompletion.create(
            engine="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a technical expert."},
                {"role": "user", "content": prompt}
            ]
        )
        
        return response['choices'][0]['message']['content']
    except Exception as e:
        return f"Error verifying code relevance: {str(e)}"

def verify_answer_correctness(question, correct_answer):
    """Verify if the provided answer is correct using GPT"""
    set_openai_api_key()  # Set the API key
    try:
        prompt = f"""
        Verify if the following answer is correct based on the question:
        
        Question: {question}
        Given Answer: {correct_answer}
        
        If the answer is incorrect, provide the correct answer with a brief explanation.
        """
        
        response = openai.ChatCompletion.create(
            engine="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a technical expert."},
                {"role": "user", "content": prompt}
            ]
        )
        
        return response['choices'][0]['message']['content']
    except Exception as e:
        return f"Error verifying answer correctness: {str(e)}"

def check_format_of_question(question_text):
    """Check if the question text indicates that code is present below"""
    phrases_to_check = [
        "the code given below",
        "the following code",
        "see the code below",
        "the code is as follows",
        "the code provided below"
    ]
    
    for phrase in phrases_to_check:
        if phrase in question_text.lower():
            return False, f"The phrase '{phrase}' should not be present in the question text."
    
    return True, "Question format is valid."

def execute_code(code):
    """Execute the provided code and return the output"""
    try:
        # Save the code to a temporary file
        with open("temp_code.py", "w") as f:
            f.write(code)
        
        # Execute the code and capture the output
        result = subprocess.run(["python", "temp_code.py"], capture_output=True, text=True)
        
        # Clean up the temporary file
        os.remove("temp_code.py")
        
        # Check if the code generates an image
        if result.returncode == 0:
            # Assuming the code saves an image as 'output.png'
            if os.path.exists("output.png"):
                return "output.png"  # Return the image path
            return result.stdout  # Return standard output if no image
        else:
            return result.stderr  # Return error output if execution fails
    except Exception as e:
        return f"Error executing code: {str(e)}"

def ai_review_code_analysis(question_content, code, question_key, correct_answer):
    """AI-based review for code analysis questions"""
    # Initialize results with all checks
    results = {
        'Format': {'status': True, 'message': 'Question format is valid'},  # Initialize format check
        'Grammar': {'status': True, 'message': 'No grammar issues found'},
        'Learning Outcome': {'status': True, 'message': 'Learning outcome is achieved'},
        'Code Relevance': {'status': True, 'message': 'Code is relevant to the question'},
        'Answer Validation': {'status': True, 'message': 'Answer appears correct'},
        'Code Execution Output': ''
    }
    
    # Check format of the question
    format_status, format_message = check_format_of_question(question_content)
    results['Format'] = {'status': format_status, 'message': format_message}
    
    # Check grammar using GPT
    grammar_status, grammar_message = check_grammar_with_gpt(question_content)
    results['Grammar']['status'] = grammar_status
    results['Grammar']['message'] = grammar_message
    
    # Verify learning outcome
    learning_outcome_message = verify_learning_outcome(question_key, question_content)
    if "not achieved" in learning_outcome_message.lower():
        results['Learning Outcome'] = {
            'status': False,
            'message': learning_outcome_message
        }
    
    # Verify code relevance
    code_relevance_message = verify_code_relevance(question_content, code)
    if "not relevant" in code_relevance_message.lower():
        results['Code Relevance'] = {
            'status': False,
            'message': code_relevance_message
        }
    
    # Verify answer correctness
    answer_correctness_message = verify_answer_with_gpt(question_content, code, correct_answer)
    if "incorrect" in answer_correctness_message.lower():
        results['Answer Validation'] = {
            'status': False,
            'message': answer_correctness_message
        }
    
    # Execute the code and capture the output
    execution_output = execute_code(code)
    results['Code Execution Output'] = execution_output
    
    return results

def display_code_analysis_results(results):
    """Display the results of the code analysis"""
    st.subheader("Code Analysis Results")
    
    for key, value in results.items():
        if value['status']:
            st.success(f"{key}: {value['message']}")
        else:
            st.warning(f"{key}: {value['message']}")

def verify_question_with_gpt(question_text):
    """Verify if the question text is correct using GPT"""
    prompt = f"Is the following question text correct? If not, please explain why: {question_text}"
    
    response = openai.ChatCompletion.create(
        engine="gpt-4o",  # Use your specific engine
        messages=[
            {"role": "system", "content": "You are a language expert."},
            {"role": "user", "content": prompt}
        ]
    )
    
    return response['choices'][0]['message']['content']

def verify_code_with_gpt(code_data):
    """Verify if the code data is correct using GPT"""
    prompt = f"Is the following code correct? If not, please explain why:\n{code_data}"
    
    response = openai.ChatCompletion.create(
        engine="gpt-4o",  # Use your specific engine
        messages=[
            {"role": "system", "content": "You are a technical expert."},
            {"role": "user", "content": prompt}
        ]
    )
    
    return response['choices'][0]['message']['content']

def verify_output_with_gpt(question_text, code_data, wrong_answers, output):
    """Verify if the output is correct based on the question and code"""
    prompt = f"""
    Question: {question_text}
    Code: {code_data}
    Wrong Answers: {wrong_answers}
    Correct Answer: {output}
    
    Is the given output correct based on the question and code? If not, please explain why. 
    If the output is the only correct answer, confirm it as correct. 
    If the correct answer lies in the wrong answers, indicate that it is incorrect.
    """
    
    response = openai.ChatCompletion.create(
        engine="gpt-4o",  # Use your specific engine
        messages=[
            {"role": "system", "content": "You are a technical expert."},
            {"role": "user", "content": prompt}
        ]
    )
    
    result = response['choices'][0]['message']['content']
    
    # Check if the output matches the expected correct answer
    if output.lower() in result.lower():
        st.success("Output is correct: " + result)  # Display in green
    else:
        # Check if the output is in the list of wrong answers
        if output in wrong_answers:
            st.warning("Output is incorrect: " + result)  # Display in yellow
        else:
            st.success("Output is correct: " + result)  # Display in green

def code_analysis_interface():
    """Interface for code analysis questions"""
    st.header("Code Analysis Question")

    # Sample question data
    question_content = "What is the effect of the given code on the grid layout?"
    code = """
    <!DOCTYPE html>
    <html>
      <head>
      <script src="https://cdn.tailwindcss.com"></script>
      </head>
      <body>
        <div class="grid grid-cols-4 gap-4">
          <div class="col-span-2">Item 1</div>
          <div class="col-span-2">Item 2</div>
        </div>
      </body>
    </html>
    """
    expected_output = "Creates a 4-column grid with two items each spanning 2 columns"

    # Display the current question and code
    st.text_area("Question Content", value=question_content, height=100)
    st.text_area("Code", value=code, height=200)

    if st.button("Analyze"):
        # Assuming you have extracted these values from your JSON or input
        question_text = "Evaluate the given code snippet. Which breakpoint prefix is intended for applying styles on the medium screens defined by Tailwind CSS?"
        code_data = """
        <!DOCTYPE html>
        <html>
          <head>
            <script src="https://cdn.tailwindcss.com"></script>
          </head>
          <body>
            <div class="text-xl ____:text-2xl">Content</div>
          </body>
        </html>
        """
        wrong_answers = ["xl", "lg", "sm"]
        output = "md"

        # Call the verification function
        verify_output_with_gpt(question_text, code_data, wrong_answers, output)

def review_fib_html_questions():
    # Check if the FIB_HTML_CODING folder exists in the uploaded ZIP
    uploaded_zip = st.file_uploader("Upload Question JSONs", type=['zip'])
    
    if uploaded_zip:
        try:
            with zipfile.ZipFile(uploaded_zip) as zip_file:
                # Look for the FIB_HTML_CODING folder
                fib_html_file = None
                for file in zip_file.namelist():
                    # Check if the file is in the FIB_HTML_CODING folder
                    if 'FIB_HTML_CODING/' in file and file.endswith('.json'):
                        fib_html_file = file
                        break
                
                if fib_html_file is None:
                    st.error("No JSON file found in the FIB_HTML_CODING folder.")
                    return
                
                with zip_file.open(fib_html_file) as json_file:
                    data = json.load(json_file)
                    
                    # Ensure data is a list
                    if not isinstance(data, list):
                        st.warning("Expected a list of questions in the JSON file.")
                        return
                    
                    fib_questions = [q for q in data if isinstance(q, dict) and q.get('question_type') == 'FIB_HTML_CODING']
                    
                    if not fib_questions:
                        st.info("No FIB HTML questions found in the JSON.")
                        return
                    
                    # Create a dropdown to select a question
                    question_options = [f"{q.get('question_id', 'Unknown')}: {q.get('question_text', 'No text')}" for q in fib_questions]
                    selected_question_index = st.selectbox("Select a FIB HTML Question", range(len(fib_questions)), format_func=lambda x: question_options[x])
                    
                    # Get the selected question
                    selected_question = fib_questions[selected_question_index]
                    
                    # Extract required fields
                    question_id = selected_question.get('question_id', 'N/A')
                    question_text = selected_question.get('question_text', 'N/A')
                    
                    # Extract initial code
                    initial_code = ""
                    fib_html_coding = selected_question.get('fib_html_coding', [])
                    if isinstance(fib_html_coding, list):
                        for code_block in fib_html_coding:
                            if isinstance(code_block, dict):  # Ensure it's a dictionary
                                for block in code_block.get('code_blocks', []):
                                    if isinstance(block, dict):  # Ensure each block is a dictionary
                                        initial_code += block.get('code', '') + "\n"
                    
                    # Extract solution code
                    solution_code = ""
                    solution = selected_question.get('solution', [])
                    if isinstance(solution, list):
                        for sol in solution:
                            if isinstance(sol, dict):  # Ensure it's a dictionary
                                for block in sol.get('code_blocks', []):
                                    if isinstance(block, dict):  # Ensure each block is a dictionary
                                        solution_code += block.get('code', '') + "\n"
                    
                    # Display the extracted information
                    st.subheader(f"Question ID: {question_id}")
                    st.write("**Question Text:**", question_text)
                    st.write("**Initial Code:**")
                    st.code(initial_code.strip(), language='html')
                    st.write("**Solution Code:**")
                    st.code(solution_code.strip(), language='html')
        except Exception as e:
            st.error(f"Error processing ZIP: {str(e)}")

def ai_review_fib_html(question_text, html_code, css_code, solution_html, solution_css, test_cases):
    """AI-based review for FIB HTML questions"""
    results = {
        'Format': {'status': True, 'message': 'Question format is valid'},
        'Grammar': {'status': True, 'message': 'No grammar issues found'},
        'Complexity': {'status': True, 'message': 'Language is appropriate'},
        'Code Keywords': {'status': True, 'message': 'Code keywords are properly formatted'},
        'Learning Outcome': {'status': True, 'message': 'Aligns with learning outcome'},
        'Fill Blank Format': {'status': True, 'message': 'Fill in the blank format is correct'},
        'Test Cases': {'status': True, 'message': 'Test cases are valid'},
        'Solution Validation': {'status': True, 'message': 'Solution code is valid'}
    }
    
    # Check if question asks to fill in the blank
    if "fill in the blank" not in question_text.lower():
        results['Fill Blank Format'] = {
            'status': False,
            'message': "Question should explicitly ask to 'fill in the blank'"
        }
    
    # Check code keywords
    code_keywords = re.findall(r'\b(?:class|id|style|div|span|HTML|CSS)\b', question_text)
    for keyword in code_keywords:
        if f"`{keyword}`" not in question_text:
            results['Code Keywords'] = {
                'status': False,
                'message': f"Keyword '{keyword}' should be in backticks"
            }
    
    # Validate test cases
    if not test_cases:
        results['Test Cases'] = {
            'status': False,
            'message': "Missing test cases"
        }
    
    # Check solution code
    if not solution_html or not solution_css:
        results['Solution Validation'] = {
            'status': False,
            'message': "Missing solution code"
        }
    
    return results

def check_complexity(text):
    """Check language complexity"""
    # Add your complexity checking logic here
    return True, "Language complexity is appropriate"

def extract_code_blocks(blocks, language):
    """Extract code blocks for a specific language"""
    code = []
    for block in blocks:
        if block.get('language') == language:
            for code_block in block.get('code_blocks', []):
                code.append(code_block.get('code', ''))
    return '\n'.join(code)

def load_questions_from_json(folder_path):
    """Load questions from a JSON file in the specified folder."""
    json_file_path = os.path.join(folder_path, 'questions.json')  # Adjust the filename as needed

    if os.path.exists(json_file_path):
        with open(json_file_path, 'r') as file:
            questions = json.load(file)
            return questions
    else:
        st.error("JSON file not found in the specified folder.")
        return []

def extract_fib_questions(questions):
    """Extract FIB questions from the list of questions."""
    fib_questions = []
    
    for question in questions:
        # Check if the question type is FIB
        if question.get('type') == 'FIB':
            fib_questions.append(question)
    
    return fib_questions

def create_database():
    conn = sqlite3.connect('cheat_sheets.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cheat_sheets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def check_mcq_relevance_with_cheat_sheet(cheat_sheet_content, mcq_question):
    """Check if the MCQ is relevant to the cheat sheet content."""
    prompt = f"Given the following cheat sheet content:\n\n{cheat_sheet_content}\n\n" \
             f"Is the following MCQ relevant to this content?\n\n" \
             f"MCQ: {mcq_question}\n" \
             f"Please respond with 'Relevant' or 'Not Relevant'."
    
    response = openai.ChatCompletion.create(
        engine="gpt-4o",  # Use your specific engine
        messages=[
            {"role": "system", "content": "You are a knowledgeable assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    
    return response['choices'][0]['message']['content'].strip()

def display_mcq_with_relevance(mcq_questions):
    """Display MCQs with relevance check against the cheat sheet."""
    for question in mcq_questions:
        relevance = check_mcq_relevance_with_cheat_sheet(cheat_sheet_content, question)
        
        if relevance.lower() == "relevant":
            st.success(f"✅ {question} - Relevant to the cheat sheet.")
        else:
            st.warning(f"⚠️ {question} - Not relevant to the cheat sheet.")

if __name__ == "__main__":
    st.set_page_config(
        page_title="NxtWave Review Platform",
        layout="wide"
    )
    create_database()  # Ensure the database is created
    main()
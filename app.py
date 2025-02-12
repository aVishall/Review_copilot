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
import time

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
        st.write("Welcome to the Review Platform!")
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
                    'fib_html': []
                }
                
                # Categorize files
                for file in file_list:
                    try:
                        with zip_file.open(file) as json_file:
                            data = json.load(json_file)
                            
                            # Ensure data is a list
                            if isinstance(data, dict):
                                data = [data]  # Convert single object to list
                            elif not isinstance(data, list):
                                st.warning(f"File {file} does not contain valid JSON data.")
                                continue
                            
                            # Process the data based on question type
                            for q in data:
                                q_type = q.get('question_type', '')
                                if q_type == 'MULTIPLE_CHOICE':
                                    question_files['default_new'].append((file, q))
                                elif q_type in ['CODE_ANALYSIS_MULTIPLE_CHOICE', 'CODE_ANALYSIS_TEXTUAL', 'CODE_ANALYSIS_MORE_THAN_ONE_MULTIPLE_CHOICE']:
                                    question_files['code_analysis'].append((file, q))
                                elif q_type == 'FIB_HTML_CODING':
                                    question_files['fib_html'].append((file, q))
                    except json.JSONDecodeError as e:
                        st.error(f"Error decoding JSON from file {file}: {str(e)}. Please check the file format.")
                    except Exception as e:
                        st.error(f"Error processing file {file}: {str(e)}")
                
                # Create separate sections for each question type
                st.subheader("Default New Questions")
                review_default_mcqs(question_files['default_new'])
                
                st.subheader("Code Analysis Questions")
                review_code_analysis_questions(question_files['code_analysis'])
                
                st.subheader("FIB HTML Coding Questions")
                review_fib_html_questions(question_files['fib_html'])
                
        except Exception as e:
            st.error(f"Error processing ZIP: {str(e)}")

def get_question_id(question):
    """Helper function to extract question_id from different possible locations in the question structure"""
    # Try different possible locations for question_id
    if 'question_id' in question:
        return question['question_id']
    elif 'input_output' in question and question['input_output'] and 'question_id' in question['input_output'][0]:
        return question['input_output'][0]['question_id']
    elif 'metadata' in question and 'question_id' in question['metadata']:
        return question['metadata']['question_id']
    elif 'id' in question:
        return question['id']
    # If no question_id is found, generate one based on the question text
    else:
        # Generate a hash of the question text to use as an ID
        question_text = question.get('question_text', '')
        if question_text:
            return f"generated_id_{hash(question_text) % 10000}"
        return "unknown_id"

def check_question_wording_with_gpt(question_text):
    """Check if question text contains inappropriate references to code location."""
    try:
        prompt = f"""
        Analyze this question text and check if it inappropriately refers to code location 
        (e.g., 'code given below', 'following code', 'code below', etc.) since the code will be shown alongside:
        
        Question: {question_text}
        
        Respond with either:
        - "OK" if there are no inappropriate references
        - Or explain what references should be removed/changed
        """
        
        response = openai.ChatCompletion.create(
            engine="gpt-4o",
            messages=[
                {"role": "system", "content": "You are analyzing question text formatting."},
                {"role": "user", "content": prompt}
            ]
        )
        
        result = response['choices'][0]['message']['content']
        return "OK" in result.upper(), result
        
    except Exception as e:
        return False, f"Error checking question wording: {str(e)}"

def display_mcq_review(question_data):
    """Enhanced display function for MCQ review"""
    st.subheader("MCQ Review")
    
    # Extract question data
    question_id = question_data.get('question_id', 'N/A')
    question_content = question_data.get('question', {}).get('content', '')
    options = question_data.get('options', [])
    question_key = question_data.get('question_key', '')
    tag_names = question_data.get('tag_names', [])
    
    # Display basic info
    st.write(f"**Question ID:** {question_id}")
    st.write("**Question:**", question_content)
    st.write("**Tags:**", ", ".join(tag_names))
    
    # Display options
    st.write("**Options:**")
    for opt in options:
        status = "✅" if opt.get('is_correct') else "❌"
        st.write(f"{status} {opt.get('content', '')}")
    
    # Perform enhanced validation
    with st.expander("Review Analysis", expanded=True):
        # Verify learning outcome
        outcome_result = verify_mcq_learning_outcome(
            question_key,
            tag_names,
            question_content
        )
        
        if outcome_result.get('achieved'):
            st.success("✅ Learning Outcome: Question aligns with tags and learning objectives")
        else:
            st.warning(f"⚠️ Learning Outcome Issues:\n{outcome_result.get('analysis')}")

def display_fib_review(question_data):
    """Enhanced display function for FIB HTML coding questions"""
    st.subheader("FIB HTML Coding Review")
    
    # Extract question data
    question_id = question_data.get('question_id', 'N/A')
    question_text = question_data.get('question_text', '')
    
    # Display basic info
    st.write(f"**Question ID:** {question_id}")
    st.write("**Question Text:**", question_text)
    
    # Display code sections
    for code_section in question_data.get('fib_html_coding', []):
        language = code_section.get('language', '')
        if language and code_section.get('code_blocks'):
            st.write(f"**{language} Code:**")
            combined_code = '\n'.join(
                block.get('code', '') 
                for block in sorted(
                    code_section.get('code_blocks', []),
                    key=lambda x: x.get('order', 0)
                )
            )
            st.code(combined_code, language=language.lower())
    
    # Perform enhanced validation
    with st.expander("Review Analysis", expanded=True):
        review_results = review_fib_html_coding(question_data)
        
        # Display technical correctness
        if review_results['technical_correctness']['status']:
            st.success("✅ Technical: Code is syntactically correct")
        else:
            st.warning(f"⚠️ Technical Issues:\n{review_results['technical_correctness']['message']}")
        
        # Display wording check
        if review_results['wording_check']['status']:
            st.success("✅ Wording: Question properly mentions fill in the blank")
        else:
            st.warning(f"⚠️ Wording: {review_results['wording_check']['message']}")
        
        # Display code reference check
        if review_results['code_reference']['status']:
            st.success("✅ Code Reference: Question properly references code")
        else:
            st.warning(f"⚠️ Code Reference: {review_results['code_reference']['message']}")
        
        # Display test case analysis
        if review_results['test_case_coverage']['status']:
            st.success("✅ Test Cases: Good coverage and validation")
        else:
            st.warning(f"⚠️ Test Cases: {review_results['test_case_coverage']['message']}")

def display_code_analysis_question(question_data):
    """Enhanced display function for code analysis questions"""
    st.subheader("Question Details")
    
    # Extract question data
    question_id = question_data.get('question_id', 'N/A')
    question_text = question_data.get('question_text', '')
    code_metadata = question_data.get('code_metadata', [])
    input_output = question_data.get('input_output', [{}])[0]
    
    # Display basic info
    st.write(f"**Question ID:** {question_id}")
    st.write("**Question Text:**", question_text)
    
    # Display code if present
    if code_metadata:
        code_data = code_metadata[0].get('code_data', '')
        language = code_metadata[0].get('language', 'text')
        st.write("**Code:**")
        st.code(code_data, language=language.lower())
    
    # Get correct answer and wrong answers
    correct_answer = input_output.get('output', [''])[0]
    wrong_answers = input_output.get('wrong_answers', [])
    
    # Perform enhanced validation
    with st.expander("Review Analysis", expanded=True):
        # Code Validation
        if code_data:
            code_validation_result = validate_code_with_gpt(code_data)
            if "CORRECT" in code_validation_result:
                st.success("✅ Code: Technically correct")
            else:
                st.warning(f"⚠️ Code Issues:\n{code_validation_result}")
        
        # Answer Verification
        if correct_answer and code_data:
            verification_result = verify_code_analysis_answer_with_gpt(
                question_text, 
                code_data, 
                correct_answer, 
                wrong_answers, 
                question_data.get('question_type', '')
            )
            
            if verification_result['is_correct']:
                st.success(f"✅ Answer: {verification_result['detailed_analysis']}")
            else:
                st.warning(f"⚠️ Answer Verification: {verification_result['detailed_analysis']}")

def verify_code_analysis_answer_with_gpt(question_text, code, correct_answer, wrong_answers, question_type):
    """Enhanced answer verification using GPT"""
    set_openai_api_key()  # Ensure API key is set
    try:
        # Prepare a comprehensive prompt for verification
        if question_type == "CODE_ANALYSIS_MULTIPLE_CHOICE":
            prompt = f"""
            Carefully analyze the following multiple choice question:
            
            Question: {question_text}
            Code: {code}
            Correct Answer: {correct_answer}
            Wrong Answers: {', '.join(wrong_answers)}
            
            Evaluation Criteria:
            1. Is the correct answer truly correct based on the code?
            2. Are there any nuances or potential ambiguities?
            3. Verify the technical accuracy of the answer
            
            Respond with:
            - "CORRECT: [Detailed explanation]" if the answer is correct
            - "INCORRECT: [Detailed explanation of why it's wrong]"
            """
        else:  # CODE_ANALYSIS_TEXTUAL
            prompt = f"""
            Carefully analyze the following textual question:
            
            Question: {question_text}
            Code: {code}
            Provided Answer: {correct_answer}
            
            Evaluation Criteria:
            1. Is the provided answer technically accurate based on the code?
            2. Are there any nuances or potential ambiguities?
            
            Respond with:
            - "CORRECT: [Detailed explanation]" if the answer is correct
            - "INCORRECT: [Detailed explanation of why it's wrong]"
            """
        
        response = openai.ChatCompletion.create(
            engine="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a technical expert in code analysis."},
                {"role": "user", "content": prompt}
            ]
        )
        
        result = response['choices'][0]['message']['content']
        
        # Determine if the answer is correct based on the response
        is_correct = "CORRECT:" in result
        
        return {
            'is_correct': is_correct,
            'detailed_analysis': result
        }
        
    except Exception as e:
        return {
            'is_correct': False,
            'detailed_analysis': f"Error verifying answer: {str(e)}"
        }
    
def verify_textual_answer_correctness(question_text, code_data, answer):
    """Verify if the textual answer is correct using GPT."""
    try:
        prompt = f"""
        Analyze this code analysis question and verify if the provided answer is correct:
        
        Question: {question_text}
        Code: {code_data}
        Provided Answer: {answer}
      
        
        Please analyze:
        1. Does the answer directly address the question?
        2. Is the answer technically accurate based on the code?
        
        
        Respond with:
        - "CORRECT: [Detailed explanation]" if the answer is correct and properly explained
        - "INCORRECT: [Detailed explanation of why it's wrong and what would be the correct answer]"
        """
        
        response = openai.ChatCompletion.create(
            engine="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a technical expert in code analysis."},
                {"role": "user", "content": prompt}
            ]
        )
        
        result = response['choices'][0]['message']['content']
        is_correct = result.strip().startswith("CORRECT:")
        
        return {
            'is_correct': is_correct,
            'detailed_analysis': result
        }
        
    except openai.error.RateLimitError as e:
        print("Rate limit exceeded. Retrying after delay...")
        time.sleep(40)  # Wait for 40 seconds before retrying
        return verify_textual_answer_correctness(question_text, code_data, answer)
    except Exception as e:
        return {
            'is_correct': False,
            'detailed_analysis': f"Error verifying answer correctness: {str(e)}"
        }

def review_code_analysis_questions(questions):
    if not questions:
        st.info("No Code Analysis questions found")
        return
        
    # Display total question count
    st.info(f"Total Code Analysis Questions: {len(questions)}")
    
    # Initialize session state for index if not exists
    if 'code_analysis_index' not in st.session_state:
        st.session_state.code_analysis_index = 0
    
    # Create dropdown with formatted question numbers and IDs
    question_options = [
        f'Question {str(i+1).zfill(2)}: {get_question_id(q[1])}' 
        for i, q in enumerate(questions)
    ]
    
    selected_index = st.selectbox(
        "Select Question",
        range(len(questions)),
        format_func=lambda x: question_options[x],
        key="code_analysis_selector",
        index=st.session_state.code_analysis_index
    )
    
    # Update session state when dropdown changes
    st.session_state.code_analysis_index = selected_index
    
    # Get the selected question
    file, question = questions[selected_index]
    
    # Extract required fields
    # Ensure question_id is extracted correctly
    question_id = (
        question.get('question_id') or 
        question.get('input_output', [{}])[0].get('question_id') or 
        question.get('metadata', {}).get('question_id') or 
        'N/A'
    )
    question_text = question.get('question_text', '')
    question_type = question.get('question_type', 'Unknown')
    code_metadata = question.get('code_metadata', [])
    input_output = question.get('input_output', [{}])[0]
    explanation = question.get('explanation', '')

    
    # Display question details
    st.subheader(f"Question Details")
    st.write(f"**Question ID:** {question_id}")
    st.write(f"**Question Type:** {question_type}")
    st.write("**Question Text:**", question_text)
    
    # Display code if present
    if code_metadata:
        code_data = code_metadata[0].get('code_data', '')
        language = code_metadata[0].get('language', 'text')
        st.write("**Code:**")
        st.code(code_data, language=language.lower())
    
    # Display options for Multiple Choice questions
    if question_type in ['CODE_ANALYSIS_MULTIPLE_CHOICE', 'CODE_ANALYSIS_MORE_THAN_ONE_MULTIPLE_CHOICE']:
        st.write("**Options:**")
        
        # Get correct and wrong answers
        correct_answer = input_output.get('output', [''])[0]
        wrong_answers = input_output.get('wrong_answers', [])
        
        # Combine and display all options
        all_options = wrong_answers + [correct_answer]
        for opt in all_options:
            # Highlight correct answer
            if opt == correct_answer:
                st.write(f"✅ {opt}")
            else:
                st.write(f"❌ {opt}")

    elif question_type == 'CODE_ANALYSIS_TEXTUAL':
        answer = input_output.get('output', [''])[0]
        st.write("Answer: " + answer)
    
    # Review Guidelines Section
    with st.expander("Review Guidelines", expanded=True):
        # 1. Grammar Check
        grammar_status, grammar_msg = check_grammar_with_gpt(question_text)
        if grammar_status:
            st.success("✅ Grammar: Question text is grammatically correct")
        else:
            st.warning(f"⚠️ Grammar: {grammar_msg}")
        
        # 2. Technical Code Check
        if code_metadata:
            code_validation_result = validate_code_with_gpt(code_data)
            if "CORRECT" in code_validation_result:
                st.success("✅ Technical: Code is technically correct")
            else:
                st.warning(f"⚠️ Technical: {code_validation_result}")
        
        # 3. Question Wording Check
        wording_status, wording_msg = check_question_wording_with_gpt(question_text)
        if wording_status:
            st.success("✅ Wording: Question text properly references code")
        else:
            st.warning(f"⚠️ Wording: {wording_msg}")
        
        # 4. Answer Verification (only for Multiple Choice)
        if question_type in ['CODE_ANALYSIS_MULTIPLE_CHOICE', 'CODE_ANALYSIS_MORE_THAN_ONE_MULTIPLE_CHOICE']:
            if correct_answer and code_data:
                verification_result = verify_code_analysis_answer_with_gpt(
                    question_text, 
                    code_data, 
                    correct_answer, 
                    wrong_answers, 
                    question_type
                )
                
                # Modify the display of answer verification
                if verification_result['is_correct']:
                    st.success(f"✅ Answer: {verification_result['detailed_analysis']}")
                else:
                    # Use warning instead of success for incorrect answers
                    st.warning(f"⚠️ Answer: {verification_result['detailed_analysis']}")

        elif question_type == 'CODE_ANALYSIS_TEXTUAL':
            if answer and code_data:
                # Verify answer correctness
                correctness_result = verify_textual_answer_correctness(
                    question_text,
                    code_data,
                    answer
                )
                print(correctness_result)

                if correctness_result['is_correct']:
                    # Use success (green) for correct answers
                    st.success(f"✅ Answer Verification: {correctness_result['detailed_analysis']}")
                else:
                    # Use warning (yellow) for incorrect answers
                    st.warning(f"⚠️ Answer Verification: {correctness_result['detailed_analysis']}")
    
    # Navigation buttons in columns
    col1, col2, col3 = st.columns([1, 4, 1])
    
    with col1:
        if st.button("← Previous", key="prev_code_analysis"):
            if st.session_state.code_analysis_index > 0:
                st.session_state.code_analysis_index -= 1
                st.rerun()
    
    with col2:
        st.write(f"Question {selected_index + 1} of {len(questions)}")
    
    with col3:
        if st.button("Next →", key="next_code_analysis"):
            if st.session_state.code_analysis_index < len(questions) - 1:
                st.session_state.code_analysis_index += 1
                st.rerun()
                
def review_fib_html_questions(questions):
    if not questions:
        st.info("No FIB HTML Coding questions found")
        return
        
    # Display total question count
    st.info(f"Total FIB HTML Coding Questions: {len(questions)}")
    
    # Initialize session state for index if not exists
    if 'fib_index' not in st.session_state:
        st.session_state.fib_index = 0
    
    # Create dropdown with formatted question numbers and IDs
    question_options = [
        f'Question {str(i+1).zfill(2)}: {q[1].get("question_id", "N/A")}' 
        for i, q in enumerate(questions)
    ]
    
    selected_index = st.selectbox(
        "Select Question",
        range(len(questions)),
        format_func=lambda x: question_options[x],
        key="fib_selector",
        index=st.session_state.fib_index
    )
    
    # Update session state when dropdown changes
    st.session_state.fib_index = selected_index
    
    # Get the selected question
    _, question = questions[selected_index]
    
    # Extract all required information
    question_id = question.get('question_id', 'N/A')
    question_text = question.get('question_text', '')
    question_key = question.get('question_key', '')
    difficulty = question.get('difficulty', '')
    tags = question.get('tag_names', [])
    
    # Display question details in an expander
    with st.expander(f"Question Details (ID: {question_id})", expanded=True):
        # Basic Information
        st.write("### Basic Information")
        st.write(f"**Question Key:** {question_key}")
        st.write(f"**Question Text:** {question_text}")
        st.write(f"**Difficulty:** {difficulty}")
        st.write("**Tags:**", ", ".join(tags))
        
        # Initial Code
        st.write("### Initial Code")
        
        # Get initial code from fib_html_coding
        initial_code = question.get('fib_html_coding', [])
        for code_block in initial_code:
            language = code_block.get('language', '')
            if language and code_block.get('code_blocks'):
                st.write(f"**{language}:**")
                combined_code = '\n'.join(
                    block.get('code', '') 
                    for block in sorted(
                        code_block.get('code_blocks', []),
                        key=lambda x: x.get('order', 0)
                    )
                )
                st.code(combined_code, language=language.lower())
        
        # Solution Code
        st.write("### Solution Code")
        
        # Get solution code
        solution_code = question.get('solution', [])
        for code_block in solution_code:
            language = code_block.get('language', '')
            if language and code_block.get('code_blocks'):
                st.write(f"**{language}:**")
                combined_code = '\n'.join(
                    block.get('code', '') 
                    for block in sorted(
                        code_block.get('code_blocks', []),
                        key=lambda x: x.get('order', 0)
                    )
                )
                st.code(combined_code, language=language.lower())
        
        # Test Cases
        st.write("### Test Cases")
        test_cases = question.get('test_cases', [])
        for test_case in test_cases:
            st.write(f"- **{test_case.get('display_text', '')}**")
            st.write(f"  - Weightage: {test_case.get('weightage', 0)}")
            st.write(f"  - Evaluation Type: {test_case.get('testcase_evaluation_type', '')}")
    
    # Navigation buttons in columns
    col1, col2, col3 = st.columns([1, 4, 1])
    
    with col1:
        if st.button("← Previous", key="prev_fib"):
            if st.session_state.fib_index > 0:
                st.session_state.fib_index -= 1
                st.rerun()
    
    with col2:
        st.write(f"Question {selected_index + 1} of {len(questions)}")
    
    with col3:
        if st.button("Next →", key="next_fib"):
            if st.session_state.fib_index < len(questions) - 1:
                st.session_state.fib_index += 1
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

def review_code_analysis_more_than_one_multiple_choice_questions(questions):
    if not questions:
        st.info("No Code Analysis More Than One Multiple Choice questions found")
        return
        
    # Display total question count
    st.info(f"Total Code Analysis More Than One Multiple Choice Questions: {len(questions)}")
    
    for _, question in questions:
        question_id = question.get('question_id', 'N/A')
        question_text = question.get('question_text', '')
        options = question.get('input_output', [{}])[0].get('wrong_answers', [])
        expected_output = question.get('input_output', [{}])[0].get('output', [''])[0]

        # Display question text and options
        st.subheader(f"Question ID: {question_id}")
        st.write(question_text)
        st.write("Options:")
        for option in options:
            st.write(f"- {option}")
        
        # Validate expected output
        if expected_output:
            st.success(f"✅ Expected output: {expected_output[0]}")
        else:
            st.warning(f"⚠️ No expected output found for question ID: {question_id}")

def review_code_analysis_textual_questions(questions):
    if not questions:
        st.info("No Code Analysis Textual questions found")
        return
        
    # Display total question count
    st.info(f"Total Code Analysis Textual Questions: {len(questions)}")
    
    for _, question in questions:
        question_id = question.get('question_id', 'N/A')
        question_text = question.get('question_text', '')
        code = question.get('code_metadata', [{}])[0].get('code_data', '')
        expected_output = question.get('input_output', [{}])[0].get('output', [''])[0]

        # Check grammar
        grammar_check_result = check_grammar_with_gpt(question_text)
        if "correct" in grammar_check_result.lower():
            st.success(f"✅ Grammar is correct for question ID: {question_id}")
        else:
            st.warning(f"⚠️ Grammar issue in question ID: {question_id}: {grammar_check_result}")

        # Validate code
        code_validation_result = validate_code_with_gpt(code)
        if "correct" in code_validation_result.lower():
            st.success(f"✅ Code is correct for question ID: {question_id}")
        else:
            st.warning(f"⚠️ Code issue in question ID: {question_id}: {code_validation_result}")

        # Validate output
        output_validation_result = validate_output_with_gpt(question_text, code, expected_output)
        if expected_output in output_validation_result:
            st.success(f"✅ Output is correct for question ID: {question_id}")
        else:
            st.warning(f"⚠️ Output issue in question ID: {question_id}: {output_validation_result}")

def validate_code_with_gpt(code, language='CSS, HTML, JavaScript, Python,SQL'):
    """Comprehensive code validation using GPT"""
    set_openai_api_key()  # Ensure API key is set
    try:
        prompt = f"""
        Perform a comprehensive validation of the following {language} code:
        
        Code: {code}
        
        Check for:
        1. Syntax errors
        2. Potential typos or incorrect property names
        3. Semantic correctness
        4. Best practices
        
        Provide a detailed analysis highlighting any issues found.
        If the code is completely correct, respond with "CORRECT: No issues detected".
        """
        
        response = openai.ChatCompletion.create(
            engine="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a code validation expert."},
                {"role": "user", "content": prompt}
            ]
        )
        
        validation_result = response['choices'][0]['message']['content']
        return validation_result
    except Exception as e:
        return f"Error validating code: {str(e)}"

if __name__ == "__main__":
    st.set_page_config(
        page_title="NxtWave Review Platform",
        layout="wide"
    )
    create_database()  # Ensure the database is created
    main()
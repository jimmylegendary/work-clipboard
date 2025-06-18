# metabase_screenshot_service.py
from flask import Flask, request, jsonify, send_file
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import base64
import time
import io
from datetime import datetime
import logging

# Configuration
METABASE_BASE_URL = "http://your-metabase.com"
DEFAULT_QUESTION_ID = "123"
DEFAULT_USERNAME = "your-username"
DEFAULT_PASSWORD = "your-password"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class MetabaseScreenshotService:
    def __init__(self):
        logger.info("Initializing Metabase Screenshot Service")
        self.firefox_options = Options()
        self.firefox_options.add_argument("--headless")
        self.firefox_options.add_argument("--no-sandbox")
        self.firefox_options.add_argument("--disable-dev-shm-usage")
        self.firefox_options.add_argument("--width=1400")
        self.firefox_options.add_argument("--height=1000")
        
        # Set real browser User-Agent
        self.firefox_options.set_preference("general.useragent.override", 
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0")
        
        logger.info("Firefox options configured")
        
    def wait_for_dynamic_elements(self, driver, max_wait=45):
        """Wait for JavaScript dynamic rendering completion with extended debugging"""
        logger.info("Step 1/3: Waiting for dynamic content loading...")
        
        # 1. Wait for page load completion
        logger.info("  - Checking document ready state")
        try:
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            logger.info("  - Document ready state: complete")
        except TimeoutException:
            logger.warning("  - Document ready state timeout, continuing...")
        
        # 2. Extended wait for JavaScript execution
        logger.info("  - Waiting 10 seconds for initial JavaScript execution")
        time.sleep(10)
        
        # 3. Check page content before form search
        try:
            page_source = driver.page_source
            logger.info(f"  - Page source length: {len(page_source)} characters")
            
            # Save full page source for debugging
            with open("full_page_source.html", "w", encoding="utf-8") as f:
                f.write(page_source)
            logger.info("  - Full page source saved: full_page_source.html")
            
            # Check for common indicators
            indicators = {
                "react": "react" in page_source.lower(),
                "vue": "vue" in page_source.lower(),
                "angular": "angular" in page_source.lower(),
                "metabase": "metabase" in page_source.lower(),
                "login": "login" in page_source.lower(),
                "username": "username" in page_source.lower(),
                "password": "password" in page_source.lower(),
                "input": page_source.lower().count("<input"),
                "form": page_source.lower().count("<form")
            }
            
            logger.info("  - Page content analysis:")
            for key, value in indicators.items():
                logger.info(f"    - {key}: {value}")
                
        except Exception as e:
            logger.error(f"  - Page analysis error: {e}")
        
        # 4. Take screenshot before form search
        try:
            driver.save_screenshot("before_form_search.png")
            logger.info("  - Screenshot saved: before_form_search.png")
        except Exception as e:
            logger.error(f"  - Screenshot error: {e}")
        
        # 5. Extended JavaScript form detection
        logger.info("  - Starting extended form detection...")
        
        extended_wait_script = """
        return new Promise((resolve) => {
            let attempts = 0;
            const maxAttempts = 150;
            
            function checkForLoginForm() {
                attempts++;
                
                const selectors = [
                    'input[name="username"]',
                    'input[name="email"]',
                    'input[name="user"]',
                    'input[name="login"]',
                    'input[type="text"]',
                    'input[type="email"]',
                    'input[placeholder*="username" i]',
                    'input[placeholder*="email" i]',
                    'input[placeholder*="user" i]',
                    'input[placeholder*="login" i]'
                ];
                
                console.log(`Attempt ${attempts}: Checking for login form...`);
                
                const allInputs = document.querySelectorAll('input');
                console.log(`Found ${allInputs.length} total input elements`);
                
                for (let selector of selectors) {
                    const element = document.querySelector(selector);
                    if (element && element.offsetParent !== null) {
                        console.log(`SUCCESS: Found login form with selector: ${selector}`);
                        resolve({
                            found: true,
                            selector: selector,
                            attempts: attempts,
                            totalInputs: allInputs.length
                        });
                        return;
                    }
                }
                
                const textInputs = document.querySelectorAll('input[type="text"], input:not([type])');
                for (let input of textInputs) {
                    if (input.offsetParent !== null && input.getBoundingClientRect().width > 0) {
                        console.log(`Found visible text input, assuming it's username field`);
                        resolve({
                            found: true,
                            selector: 'input[type="text"]',
                            attempts: attempts,
                            totalInputs: allInputs.length,
                            assumedLogin: true
                        });
                        return;
                    }
                }
                
                if (attempts < maxAttempts) {
                    setTimeout(checkForLoginForm, 300);
                } else {
                    console.log(`FAILED: No login form found after ${attempts} attempts`);
                    resolve({
                        found: false, 
                        attempts: attempts,
                        totalInputs: allInputs.length,
                        finalUrl: window.location.href,
                        finalTitle: document.title
                    });
                }
            }
            
            checkForLoginForm();
        });
        """
        
        try:
            logger.info("  - Executing extended JavaScript form detection...")
            result = driver.execute_async_script(extended_wait_script)
            
            logger.info(f"  - Form detection result:")
            logger.info(f"    - Found: {result.get('found', False)}")
            logger.info(f"    - Attempts: {result.get('attempts', 0)}")
            logger.info(f"    - Total inputs: {result.get('totalInputs', 0)}")
            logger.info(f"    - Selector: {result.get('selector', 'N/A')}")
            logger.info(f"    - Assumed login: {result.get('assumedLogin', False)}")
            
            if result.get('found'):
                logger.info(f"  - SUCCESS: Login form found with selector: {result.get('selector')}")
            else:
                logger.error(f"  - FAILED: No login form found")
                logger.error(f"    - Final URL: {result.get('finalUrl', 'N/A')}")
                logger.error(f"    - Final title: {result.get('finalTitle', 'N/A')}")
                
                try:
                    driver.save_screenshot("form_search_failed.png")
                    logger.info("  - Final screenshot saved: form_search_failed.png")
                except:
                    pass
            
            return result
            
        except Exception as e:
            logger.error(f"  - JavaScript execution error: {e}")
            return {"found": False, "error": str(e)}
    
    def login_to_metabase(self, driver, username, password):
        """Login to Metabase with enhanced debugging"""
        login_url = f"{METABASE_BASE_URL}/auth/login"
        logger.info(f"Step 2/3: Starting login process")
        logger.info(f"  - Target URL: {login_url}")
        
        try:
            logger.info("  - Loading login page...")
            driver.get(login_url)
            time.sleep(3)
            
            current_url = driver.current_url
            page_title = driver.title
            logger.info(f"  - Current URL: {current_url}")
            logger.info(f"  - Page title: {page_title}")
            
            if "404" in page_title or "not found" in page_title.lower() or "error" in current_url.lower():
                logger.error(f"  - Page load failed - error detected")
                return False
            
            logger.info(f"  - Page loaded successfully")
            
        except Exception as e:
            logger.error(f"  - Failed to load login page: {e}")
            return False
        
        # Wait for dynamic elements
        logger.info("  - Starting form detection with extended debugging...")
        form_result = self.wait_for_dynamic_elements(driver)
        
        if not form_result.get("found"):
            logger.error("  - LOGIN FORM NOT FOUND - Starting extensive debugging...")
            
            try:
                all_inputs = driver.find_elements(By.TAG_NAME, "input")
                logger.info(f"    - Total input elements found: {len(all_inputs)}")
                
                for i, inp in enumerate(all_inputs):
                    try:
                        element_info = {
                            "index": i,
                            "type": inp.get_attribute("type"),
                            "name": inp.get_attribute("name"),
                            "id": inp.get_attribute("id"),
                            "class": inp.get_attribute("class"),
                            "placeholder": inp.get_attribute("placeholder"),
                            "displayed": inp.is_displayed(),
                            "enabled": inp.is_enabled()
                        }
                        logger.info(f"    - Input {i}: {element_info}")
                    except Exception as e:
                        logger.error(f"    - Input {i}: Error - {e}")
                
                final_source = driver.page_source
                with open("login_failed_source.html", "w", encoding="utf-8") as f:
                    f.write(final_source)
                logger.info("  - Failed page source saved: login_failed_source.html")
                
                driver.save_screenshot("login_failed_screenshot.png")
                logger.info("  - Failed screenshot saved: login_failed_screenshot.png")
                
            except Exception as e:
                logger.error(f"    - Debugging failed: {e}")
            
            return False
        
        logger.info(f"  - Login form detected successfully")
        
        # Find username field
        logger.info("  - Searching for username field...")
        detected_selector = form_result.get('selector')
        username_element = None
        
        if detected_selector:
            try:
                logger.info(f"    - Trying detected selector: {detected_selector}")
                username_element = driver.find_element(By.CSS_SELECTOR, detected_selector)
                if username_element.is_displayed() and username_element.is_enabled():
                    logger.info(f"    - SUCCESS with detected selector")
                else:
                    username_element = None
            except Exception as e:
                logger.warning(f"    - Failed with detected selector: {e}")
        
        if not username_element:
            username_selectors = [
                (By.NAME, "username"),
                (By.NAME, "email"),
                (By.CSS_SELECTOR, "input[type='text']"),
                (By.CSS_SELECTOR, "input[type='email']")
            ]
            
            for i, (selector_type, selector_value) in enumerate(username_selectors, 1):
                logger.info(f"    - Fallback attempt {i}: {selector_type.name}='{selector_value}'")
                try:
                    username_element = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    logger.info(f"    - SUCCESS with fallback selector")
                    break
                except TimeoutException:
                    continue
        
        if not username_element:
            logger.error("  - Username field not found")
            return False
        
        # Find password field
        logger.info("  - Searching for password field...")
        try:
            password_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
            )
            logger.info("  - Password field found successfully")
        except TimeoutException:
            logger.error("  - Password field not found")
            return False
        
        # Input credentials
        logger.info("  - Entering credentials...")
        try:
            username_element.clear()
            username_element.send_keys(username)
            logger.info(f"  - Username entered: {username}")
            
            password_element.clear()
            password_element.send_keys(password)
            logger.info("  - Password entered: [HIDDEN]")
        except Exception as e:
            logger.error(f"  - Failed to enter credentials: {e}")
            return False
        
        # Submit form
        logger.info("  - Submitting login form...")
        try:
            submit_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
            )
            submit_button.click()
            logger.info("  - Submit button clicked")
        except TimeoutException:
            logger.info("  - Submit button not found, trying Enter key...")
            password_element.send_keys("\n")
            logger.info("  - Enter key pressed")
        
        # Wait and verify login
        logger.info("  - Waiting for login completion...")
        time.sleep(5)
        
        current_url = driver.current_url
        if "/auth/login" not in current_url:
            logger.info(f"  - Login successful! New URL: {current_url}")
            return True
        else:
            logger.error(f"  - Login failed - still on login page: {current_url}")
            return False
    
    def wait_for_question_load(self, driver, wait_seconds=10):
        """Wait for Question page chart loading completion"""
        logger.info("Step 3/3: Loading question chart...")
        
        logger.info("  - Searching for chart elements...")
        chart_selectors = [
            ".Visualization",
            "[data-testid='query-visualization-root']", 
            ".QueryBuilder-section",
            ".Card .Card-content",
            "svg",
            "canvas"
        ]
        
        chart_found = False
        for i, selector in enumerate(chart_selectors, 1):
            logger.info(f"    - Attempt {i}/{len(chart_selectors)}: Looking for '{selector}'")
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                logger.info(f"    - SUCCESS: Chart element found with '{selector}'")
                chart_found = True
                break
            except TimeoutException:
                logger.info(f"    - Failed: Timeout for '{selector}'")
                continue
        
        if not chart_found:
            logger.warning("  - No chart elements found, but continuing process")
        
        logger.info("  - Checking for loading spinners...")
        try:
            WebDriverWait(driver, 10).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".Loading, .LoadingSpinner, [data-testid='loading-spinner']"))
            )
            logger.info("  - Loading spinners disappeared")
        except TimeoutException:
            logger.info("  - Loading spinner check timeout, continuing...")
        
        logger.info(f"  - Additional safety wait: {wait_seconds} seconds")
        time.sleep(wait_seconds)
        
        logger.info("  - Verifying chart rendering with JavaScript...")
        try:
            is_ready = driver.execute_script("""
                const charts = document.querySelectorAll('svg, canvas, .Visualization');
                return {
                    count: charts.length,
                    ready: charts.length > 0
                };
            """)
            
            if is_ready.get('ready'):
                logger.info(f"  - Chart rendering verified: {is_ready.get('count')} chart elements found")
            else:
                logger.warning("  - No chart elements found in JavaScript verification")
        except Exception as e:
            logger.error(f"  - JavaScript verification error: {e}")
    
    def capture_question_chart(self, driver):
        """Enhanced chart area capture with better detection"""
        logger.info("  - Starting enhanced chart area capture...")
        
        try:
            time.sleep(2)
            
            chart_selectors = [
                ".Visualization",
                "[data-testid='query-visualization-root']",
                ".Card .Visualization",
                "svg[class*='chart']",
                "svg[class*='visualization']", 
                ".Visualization svg",
                "canvas[class*='chart']",
                ".Visualization canvas",
                ".QueryBuilder-section .Card",
                ".Card .Card-content",
                ".Question .Card",
                ".DashCard .Card-content"
            ]
            
            chart_element = None
            successful_selector = None
            
            for i, selector in enumerate(chart_selectors, 1):
                logger.info(f"    - Chart detection attempt {i}/{len(chart_selectors)}: '{selector}'")
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    logger.info(f"      - Found {len(elements)} elements")
                    
                    for j, element in enumerate(elements):
                        try:
                            size = element.size
                            location = element.location
                            is_displayed = element.is_displayed()
                            
                            logger.info(f"      - Element {j+1}: size={size}, location={location}, displayed={is_displayed}")
                            
                            if (is_displayed and 
                                size['width'] > 200 and size['height'] > 150 and
                                location['x'] >= 0 and location['y'] >= 0):
                                
                                chart_element = element
                                successful_selector = selector
                                logger.info(f"    - SUCCESS: Chart element selected")
                                logger.info(f"      - Selector: '{selector}'")
                                logger.info(f"      - Final size: {size}")
                                break
                                
                        except Exception as e:
                            logger.info(f"      - Element {j+1}: Error checking - {e}")
                            continue
                    
                    if chart_element:
                        break
                        
                except Exception as e:
                    logger.info(f"      - Selector error: {e}")
                    continue
            
            if chart_element:
                logger.info("  - Capturing chart element screenshot...")
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", chart_element)
                    time.sleep(1)
                    
                    screenshot_data = chart_element.screenshot_as_png
                    logger.info(f"  - Chart area screenshot captured successfully using: {successful_selector}")
                    return screenshot_data
                    
                except Exception as e:
                    logger.error(f"  - Chart element screenshot failed: {e}")
                    return driver.get_screenshot_as_png()
            else:
                logger.warning("  - No suitable chart element found, capturing full page")
                return driver.get_screenshot_as_png()
                
        except Exception as e:
            logger.error(f"  - Chart capture completely failed: {e}")
            return driver.get_screenshot_as_png()
    
    def capture_question(self, question_id=None, username=None, password=None, wait_seconds=10, crop_to_chart=True):
        """Capture Question URL as PNG"""
        logger.info("="*60)
        logger.info("STARTING METABASE SCREENSHOT CAPTURE")
        logger.info("="*60)
        
        question_id = question_id or DEFAULT_QUESTION_ID
        username = username or DEFAULT_USERNAME
        password = password or DEFAULT_PASSWORD
        
        logger.info(f"Configuration:")
        logger.info(f"  - Base URL: {METABASE_BASE_URL}")
        logger.info(f"  - Question ID: {question_id}")
        logger.info(f"  - Username: {username}")
        logger.info(f"  - Wait seconds: {wait_seconds}")
        logger.info(f"  - Crop to chart: {crop_to_chart}")
        
        logger.info("Initializing Firefox WebDriver...")
        try:
            driver = webdriver.Firefox(options=self.firefox_options)
            logger.info("Firefox WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Firefox WebDriver: {e}")
            raise
        
        try:
            # Login
            logger.info("\n" + "="*40)
            logger.info("PHASE 1: AUTHENTICATION")
            logger.info("="*40)
            
            if not self.login_to_metabase(driver, username, password):
                raise Exception("Authentication failed")
            
            logger.info("Authentication completed successfully!")
            
            # Navigate to Question page
            logger.info("\n" + "="*40)
            logger.info("PHASE 2: NAVIGATION")
            logger.info("="*40)
            
            question_url = f"{METABASE_BASE_URL}/question/{question_id}"
            logger.info(f"Navigating to Question page: {question_url}")
            
            try:
                driver.get(question_url)
                logger.info("Question page loaded successfully")
                logger.info(f"Current URL: {driver.current_url}")
            except Exception as e:
                logger.error(f"Failed to load question page: {e}")
                raise
            
            # Wait for chart loading completion
            logger.info("\n" + "="*40)
            logger.info("PHASE 3: CHART LOADING")
            logger.info("="*40)
            
            self.wait_for_question_load(driver, wait_seconds)
            logger.info("Chart loading phase completed")
            
            # Capture screenshot
            logger.info("\n" + "="*40)
            logger.info("PHASE 4: SCREENSHOT CAPTURE")
            logger.info("="*40)
            
            if crop_to_chart:
                logger.info("Capturing chart area only...")
                screenshot_png = self.capture_question_chart(driver)
            else:
                logger.info("Capturing full page...")
                screenshot_png = driver.get_screenshot_as_png()
            
            screenshot_size = len(screenshot_png)
            logger.info(f"Screenshot captured successfully")
            logger.info(f"Screenshot size: {screenshot_size:,} bytes ({screenshot_size/1024:.1f} KB)")
            
            logger.info("\n" + "="*60)
            logger.info("SCREENSHOT CAPTURE COMPLETED SUCCESSFULLY!")
            logger.info("="*60)
            
            return screenshot_png
                
        except Exception as e:
            logger.error(f"\n" + "="*60)
            logger.error("SCREENSHOT CAPTURE FAILED!")
            logger.error("="*60)
            logger.error(f"Error: {e}")
            
            try:
                driver.save_screenshot("capture_error.png")
                logger.info("Error screenshot saved: capture_error.png")
            except:
                logger.error("Failed to save error screenshot")
            
            raise
        finally:
            logger.info("Closing Firefox WebDriver...")
            try:
                driver.quit()
                logger.info("Firefox WebDriver closed successfully")
            except:
                logger.error("Failed to close Firefox WebDriver")

# Service instance
screenshot_service = MetabaseScreenshotService()

@app.route('/screenshot', methods=['POST'])
def take_screenshot():
    """API to convert Question to PNG"""
    request_id = int(time.time())
    logger.info(f"\n" + "+"*60)
    logger.info(f"NEW API REQUEST - ID: {request_id}")
    logger.info("+"*60)
    
    try:
        data = request.json or {}
        question_id = data.get('question_id')
        username = data.get('username')
        password = data.get('password')
        wait_seconds = data.get('wait_seconds', 10)
        crop_to_chart = data.get('crop_to_chart', True)
        return_base64 = data.get('return_base64', True)
        
        logger.info(f"Request parameters:")
        logger.info(f"  - Question ID: {question_id or DEFAULT_QUESTION_ID}")
        logger.info(f"  - Username: {username or DEFAULT_USERNAME}")
        logger.info(f"  - Wait seconds: {wait_seconds}")
        logger.info(f"  - Crop to chart: {crop_to_chart}")
        logger.info(f"  - Return Base64: {return_base64}")
        
        start_time = time.time()
        screenshot_png = screenshot_service.capture_question(
            question_id=question_id,
            username=username,
            password=password,
            wait_seconds=wait_seconds,
            crop_to_chart=crop_to_chart
        )
        end_time = time.time()
        
        total_time = end_time - start_time
        logger.info(f"Total processing time: {total_time:.2f} seconds")
        
        if return_base64:
            logger.info("Converting to Base64...")
            image_base64 = base64.b64encode(screenshot_png).decode()
            logger.info(f"Base64 conversion completed: {len(image_base64):,} characters")
            
            response = {
                "success": True,
                "image_base64": image_base64,
                "timestamp": datetime.now().isoformat(),
                "question_id": question_id or DEFAULT_QUESTION_ID,
                "base_url": METABASE_BASE_URL,
                "processing_time": round(total_time, 2),
                "image_size": len(screenshot_png)
            }
            
            logger.info(f"API Request {request_id} completed successfully")
            return jsonify(response)
        else:
            logger.info("Returning binary file...")
            filename = f'metabase_question_{question_id or DEFAULT_QUESTION_ID}_{int(time.time())}.png'
            logger.info(f"Filename: {filename}")
            
            return send_file(
                io.BytesIO(screenshot_png),
                mimetype='image/png',
                as_attachment=True,
                download_name=filename
            )
            
    except Exception as e:
        logger.error(f"API Request {request_id} failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "request_id": request_id,
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Service health check"""
    logger.info("Health check requested")
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Metabase Screenshot Service",
        "base_url": METABASE_BASE_URL,
        "default_question_id": DEFAULT_QUESTION_ID
    })

@app.route('/test', methods=['POST'])
def test_login():
    """Login test endpoint"""
    logger.info("Login test requested")
    
    try:
        data = request.json or {}
        username = data.get('username') or DEFAULT_USERNAME
        password = data.get('password') or DEFAULT_PASSWORD
        
        logger.info(f"Testing login with username: {username}")
        
        driver = webdriver.Firefox(options=screenshot_service.firefox_options)
        
        try:
            result = screenshot_service.login_to_metabase(driver, username, password)
            
            response = {
                "success": result,
                "message": "Login successful" if result else "Login failed",
                "current_url": driver.current_url,
                "base_url": METABASE_BASE_URL,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Login test result: {'SUCCESS' if result else 'FAILED'}")
            return jsonify(response)
            
        finally:
            driver.quit()
            
    except Exception as e:
        logger.error(f"Login test error: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    logger.info("Configuration requested")
    return jsonify({
        "base_url": METABASE_BASE_URL,
        "default_question_id": DEFAULT_QUESTION_ID,
        "default_username": DEFAULT_USERNAME
    })

@app.route('/diagnose', methods=['POST'])
def diagnose_login():
    """Quick diagnosis of login page"""
    try:
        data = request.json or {}
        
        driver = webdriver.Firefox(options=screenshot_service.firefox_options)
        
        try:
            login_url = f"{METABASE_BASE_URL}/auth/login"
            logger.info(f"Diagnosing: {login_url}")
            
            driver.get(login_url)
            time.sleep(5)
            
            current_url = driver.current_url
            title = driver.title
            page_source = driver.page_source
            
            driver.save_screenshot("diagnosis.png")
            with open("diagnosis.html", "w", encoding="utf-8") as f:
                f.write(page_source)
            
            inputs = driver.find_elements(By.TAG_NAME, "input")
            input_info = []
            for i, inp in enumerate(inputs):
                try:
                    input_info.append({
                        "index": i,
                        "type": inp.get_attribute("type"),
                        "name": inp.get_attribute("name"),
                        "id": inp.get_attribute("id"),
                        "class": inp.get_attribute("class"),
                        "placeholder": inp.get_attribute("placeholder"),
                        "displayed": inp.is_displayed(),
                        "enabled": inp.is_enabled()
                    })
                except:
                    input_info.append({"index": i, "error": "Could not read attributes"})
            
                        return jsonify({
                "success": True,
                "url": current_url,
                "title": title,
                "page_size": len(page_source),
                "input_count": len(inputs),
                "inputs": input_info,
                "has_username": "username" in page_source.lower(),
                "has_password": "password" in page_source.lower(),
                "has_login": "login" in page_source.lower(),
                "has_form": "<form" in page_source.lower()
            })
            
        finally:
            driver.quit()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/debug-chart', methods=['POST'])
def debug_chart_detection():
    """Debug endpoint to analyze chart elements on page"""
    try:
        data = request.json or {}
        question_id = data.get('question_id') or DEFAULT_QUESTION_ID
        username = data.get('username') or DEFAULT_USERNAME
        password = data.get('password') or DEFAULT_PASSWORD
        
        driver = webdriver.Firefox(options=screenshot_service.firefox_options)
        
        try:
            if not screenshot_service.login_to_metabase(driver, username, password):
                return jsonify({"error": "Login failed"}), 500
            
            question_url = f"{METABASE_BASE_URL}/question/{question_id}"
            driver.get(question_url)
            time.sleep(10)
            
            analysis_script = """
            const allElements = document.querySelectorAll('*');
            const candidates = [];
            
            for (let element of allElements) {
                const rect = element.getBoundingClientRect();
                const style = window.getComputedStyle(element);
                
                if (rect.width > 100 && rect.height > 100 && 
                    style.display !== 'none' && style.visibility !== 'hidden') {
                    
                    candidates.push({
                        tagName: element.tagName,
                        className: element.className,
                        id: element.id,
                        width: rect.width,
                        height: rect.height,
                        x: rect.x,
                        y: rect.y,
                        hasChart: element.querySelector('svg, canvas') !== null,
                        chartCount: element.querySelectorAll('svg, canvas').length
                    });
                }
            }
            
            return candidates.sort((a, b) => (b.width * b.height) - (a.width * a.height));
            """
            
            candidates = driver.execute_script(analysis_script)
            
            return jsonify({
                "success": True,
                "candidates": candidates[:20],
                "total_candidates": len(candidates)
            })
            
        finally:
            driver.quit()
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    logger.info("="*60)
    logger.info("METABASE SCREENSHOT SERVICE STARTING")
    logger.info("="*60)
    logger.info("Available endpoints:")
    logger.info("   POST /screenshot - Convert Question to PNG")
    logger.info("   POST /test - Login test")
    logger.info("   POST /diagnose - Quick login page diagnosis")
    logger.info("   POST /debug-chart - Debug chart element detection")
    logger.info("   GET /health - Service health check")
    logger.info("   GET /config - View current configuration")
    logger.info(f"Configuration:")
    logger.info(f"   Base URL: {METABASE_BASE_URL}")
    logger.info(f"   Default Question ID: {DEFAULT_QUESTION_ID}")
    logger.info(f"   Default Username: {DEFAULT_USERNAME}")
    logger.info("="*60)
    logger.info("Server starting on: http://0.0.0.0:5000")
    logger.info("="*60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)

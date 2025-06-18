# metabase_screenshot_service.py
from flask import Flask, request, jsonify, send_file
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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
        logger.info("Firefox options configured")
        
    def dismiss_popups(self, driver):
        """Dismiss any popups that might appear"""
        logger.info("Checking for popups to dismiss...")
        
        # Common popup selectors to try
        popup_selectors = [
            # Close buttons
            "button[aria-label='Close']",
            "button[aria-label='close']",
            "[data-testid='close-button']",
            "[data-testid='modal-close']",
            ".close-button",
            ".modal-close",
            "button.close",
            
            # Dismiss/Cancel buttons
            "button[aria-label='Dismiss']",
            "button[aria-label='Cancel']",
            "button:contains('Close')",
            "button:contains('Dismiss')",
            "button:contains('Cancel')",
            "button:contains('Skip')",
            "button:contains('Later')",
            "button:contains('No thanks')",
            
            # Modal overlay (click to close)
            ".modal-backdrop",
            ".overlay",
            
            # Specific Metabase popups
            "[data-testid='onboarding-modal'] button",
            "[data-testid='tutorial-modal'] button",
            ".onboarding-modal button",
            ".tutorial-modal button",
            
            # Generic modal close
            ".modal button",
            ".popup button",
            ".dialog button"
        ]
        
        popup_dismissed = False
        
        for selector in popup_selectors:
            try:
                # Wait briefly for popup to appear
                popup_element = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                
                if popup_element.is_displayed():
                    popup_element.click()
                    logger.info(f"Popup dismissed using selector: {selector}")
                    popup_dismissed = True
                    time.sleep(1)  # Wait for popup to close
                    break
                    
            except TimeoutException:
                continue
            except Exception as e:
                logger.info(f"Could not click popup with selector {selector}: {e}")
                continue
        
        # Try ESC key as fallback
        if not popup_dismissed:
            try:
                from selenium.webdriver.common.keys import Keys
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                logger.info("Tried ESC key to dismiss popup")
                time.sleep(1)
            except:
                pass
        
        # Additional JavaScript approach to close modals
        try:
            driver.execute_script("""
                // Try to close any visible modals
                const modals = document.querySelectorAll('.modal, .popup, .dialog, [role="dialog"]');
                modals.forEach(modal => {
                    if (modal.style.display !== 'none') {
                        const closeBtn = modal.querySelector('button[aria-label*="close"], button[aria-label*="Close"], .close, .close-button');
                        if (closeBtn) closeBtn.click();
                    }
                });
                
                // Hide overlay elements
                const overlays = document.querySelectorAll('.modal-backdrop, .overlay');
                overlays.forEach(overlay => overlay.style.display = 'none');
            """)
            logger.info("Executed JavaScript popup dismissal")
        except Exception as e:
            logger.info(f"JavaScript popup dismissal failed: {e}")
        
        return popup_dismissed
        
    def login_to_metabase(self, driver, username, password):
        """Simple login based on Gist approach"""
        login_url = f"{METABASE_BASE_URL}/auth/login"
        logger.info(f"Navigating to login page: {login_url}")
        
        try:
            driver.get(login_url)
            logger.info("Login page loaded")
            
            # Wait for page to load completely
            time.sleep(3)
            
            # Dismiss any popups that might appear on login page
            self.dismiss_popups(driver)
            
            # Find username field - try multiple approaches
            username_element = None
            username_selectors = [
                "input[name='username']",
                "input[name='email']", 
                "input[type='email']",
                "input[type='text']"
            ]
            
            for selector in username_selectors:
                try:
                    username_element = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"Username field found: {selector}")
                    break
                except TimeoutException:
                    continue
            
            if not username_element:
                logger.error("Username field not found")
                return False
            
            # Find password field
            try:
                password_element = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
                )
                logger.info("Password field found")
            except TimeoutException:
                logger.error("Password field not found")
                return False
            
            # Enter credentials
            logger.info("Entering credentials...")
            username_element.clear()
            username_element.send_keys(username)
            
            password_element.clear()
            password_element.send_keys(password)
            
            # Submit form - try button first, then Enter key
            try:
                submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                submit_button.click()
                logger.info("Submit button clicked")
            except:
                logger.info("Submit button not found, using Enter key")
                password_element.send_keys("\n")
            
            # Wait for login to complete
            time.sleep(3)
            
            # Dismiss any post-login popups
            self.dismiss_popups(driver)
            
            # Check if login was successful
            current_url = driver.current_url
            if "/auth/login" not in current_url:
                logger.info(f"Login successful! Current URL: {current_url}")
                return True
            else:
                logger.error("Login failed - still on login page")
                return False
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    def wait_for_chart_load(self, driver, wait_seconds=10):
        """Wait for chart to load on question page"""
        logger.info("Waiting for chart to load...")
        
        # Dismiss any popups that might appear on question page
        time.sleep(2)  # Brief wait for page to stabilize
        self.dismiss_popups(driver)
        
        # Wait for visualization elements
        chart_selectors = [
            ".Visualization",
            "svg",
            "canvas",
            ".Card .Card-content"
        ]
        
        chart_found = False
        for selector in chart_selectors:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                logger.info(f"Chart element found: {selector}")
                chart_found = True
                break
            except TimeoutException:
                continue
        
        if not chart_found:
            logger.warning("No chart elements found, but continuing...")
        
        # Additional wait for chart rendering
        logger.info(f"Additional wait for chart rendering: {wait_seconds} seconds")
        time.sleep(wait_seconds)
        
        # Final popup check before screenshot
        self.dismiss_popups(driver)
        
        return chart_found
    
    def capture_chart_area(self, driver):
        """Capture chart area or full page"""
        logger.info("Capturing screenshot...")
        
        # Final popup dismissal before capture
        self.dismiss_popups(driver)
        
        # Try to find and capture chart area
        chart_selectors = [
            ".Visualization",
            ".Card .Card-content",
            ".QueryBuilder-section .Card",
            ".Question .Card"
        ]
        
        for selector in chart_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed() and element.size['width'] > 200 and element.size['height'] > 150:
                        logger.info(f"Capturing chart element: {selector}")
                        return element.screenshot_as_png
            except Exception as e:
                logger.info(f"Error with selector {selector}: {e}")
                continue
        
        # Fallback to full page
        logger.info("Capturing full page screenshot")
        return driver.get_screenshot_as_png()
    
    def capture_question(self, question_id=None, username=None, password=None, wait_seconds=10, crop_to_chart=True):
        """Main function to capture question as PNG"""
        logger.info("Starting screenshot capture process")
        
        # Use defaults if not provided
        question_id = question_id or DEFAULT_QUESTION_ID
        username = username or DEFAULT_USERNAME
        password = password or DEFAULT_PASSWORD
        
        logger.info(f"Target: {METABASE_BASE_URL}/question/{question_id}")
        logger.info(f"Username: {username}")
        
        # Initialize driver
        logger.info("Creating Firefox driver...")
        driver = webdriver.Firefox(options=self.firefox_options)
        
        try:
            # Step 1: Login
            logger.info("Step 1: Login")
            if not self.login_to_metabase(driver, username, password):
                raise Exception("Login failed")
            
            # Step 2: Navigate to question
            logger.info("Step 2: Navigate to question")
            question_url = f"{METABASE_BASE_URL}/question/{question_id}"
            driver.get(question_url)
            logger.info(f"Question page loaded: {driver.current_url}")
            
            # Step 3: Wait for chart and dismiss popups
            logger.info("Step 3: Wait for chart to load and dismiss popups")
            self.wait_for_chart_load(driver, wait_seconds)
            
            # Step 4: Final popup check and capture screenshot
            logger.info("Step 4: Final popup dismissal and capture screenshot")
            self.dismiss_popups(driver)  # One more time before capture
            
            if crop_to_chart:
                screenshot_data = self.capture_chart_area(driver)
            else:
                screenshot_data = driver.get_screenshot_as_png()
            
            logger.info(f"Screenshot captured: {len(screenshot_data)} bytes")
            return screenshot_data
            
        except Exception as e:
            logger.error(f"Capture failed: {e}")
            # Save error screenshot
            try:
                driver.save_screenshot("error_screenshot.png")
                logger.info("Error screenshot saved: error_screenshot.png")
            except:
                pass
            raise
        finally:
            logger.info("Closing driver")
            driver.quit()

# Service instance
screenshot_service = MetabaseScreenshotService()

@app.route('/screenshot', methods=['POST'])
def take_screenshot():
    """API endpoint to capture screenshot"""
    logger.info("Screenshot API called")
    
    try:
        data = request.json or {}
        question_id = data.get('question_id')
        username = data.get('username') 
        password = data.get('password')
        wait_seconds = data.get('wait_seconds', 10)
        crop_to_chart = data.get('crop_to_chart', True)
        return_base64 = data.get('return_base64', True)
        
        # Capture screenshot
        start_time = time.time()
        screenshot_png = screenshot_service.capture_question(
            question_id=question_id,
            username=username,
            password=password,
            wait_seconds=wait_seconds,
            crop_to_chart=crop_to_chart
        )
        end_time = time.time()
        
        if return_base64:
            image_base64 = base64.b64encode(screenshot_png).decode()
            return jsonify({
                "success": True,
                "image_base64": image_base64,
                "timestamp": datetime.now().isoformat(),
                "question_id": question_id or DEFAULT_QUESTION_ID,
                "processing_time": round(end_time - start_time, 2),
                "image_size": len(screenshot_png)
            })
        else:
            filename = f'metabase_question_{question_id or DEFAULT_QUESTION_ID}.png'
            return send_file(
                io.BytesIO(screenshot_png),
                mimetype='image/png',
                as_attachment=True,
                download_name=filename
            )
            
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/test', methods=['POST'])
def test_login():
    """Test login functionality"""
    logger.info("Login test requested")
    
    try:
        data = request.json or {}
        username = data.get('username') or DEFAULT_USERNAME
        password = data.get('password') or DEFAULT_PASSWORD
        
        driver = webdriver.Firefox(options=screenshot_service.firefox_options)
        
        try:
            result = screenshot_service.login_to_metabase(driver, username, password)
            return jsonify({
                "success": result,
                "message": "Login successful" if result else "Login failed",
                "current_url": driver.current_url,
                "timestamp": datetime.now().isoformat()
            })
        finally:
            driver.quit()
            
    except Exception as e:
        logger.error(f"Test login error: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Metabase Screenshot Service"
    })

@app.route('/config', methods=['GET'])
def get_config():
    """Get configuration"""
    return jsonify({
        "base_url": METABASE_BASE_URL,
        "default_question_id": DEFAULT_QUESTION_ID,
        "default_username": DEFAULT_USERNAME
    })

if __name__ == '__main__':
    logger.info("Starting Metabase Screenshot Service")
    logger.info(f"Base URL: {METABASE_BASE_URL}")
    logger.info("Available endpoints:")
    logger.info("  POST /screenshot - Capture question screenshot")
    logger.info("  POST /test - Test login")
    logger.info("  GET /health - Health check")
    logger.info("  GET /config - View config")
    logger.info("Server starting on http://0.0.0.0:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=False)

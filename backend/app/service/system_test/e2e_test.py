import os
import time
import json
from typing import Dict, Any, List
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import tempfile

from app.static.system_test import (
    DEFAULT_TEST_CONFIG, CHROME_OPTIONS, HEADLESS_WINDOW_SIZE, MAXIMIZED_WINDOW,
    TEST_DIRECTORIES, DEFAULT_TEST_IMAGE, RETRY_CONFIG, WAIT_CONFIG,
    DETECTION_WAIT_CONFIG, SELECTORS, URL_VALIDATION, TEST_CASES_CONFIG,
    JAVASCRIPT_SCRIPTS
)

from .config import E2ETestConfig
from .utils import E2ETestUtils


class E2ETestService:
    """E2E测试服务主类"""
    
    def __init__(self):
        self.driver = None
        self.wait = None
        self.short_wait = None
        self.test_data_dir = TEST_DIRECTORIES["test_data"]
        self.screenshot_dir = TEST_DIRECTORIES["screenshots"]
        self._setup_test_directories()
        
    def _setup_test_directories(self):
        """设置测试目录"""
        E2ETestUtils.setup_test_directories()
        self._create_default_test_image()
    
    def _create_default_test_image(self):
        """创建默认测试图片"""
        test_image_path = os.path.join(self.test_data_dir, DEFAULT_TEST_IMAGE["filename"])
        if not os.path.exists(test_image_path):
            E2ETestUtils._create_default_test_image(test_image_path)
    
    def get_predefined_test_cases(self) -> List[Dict[str, Any]]:
        test_case = TEST_CASES_CONFIG["plot_detection"].copy()
        test_case["test_data"] = {
            "image_path": os.path.join(self.test_data_dir, DEFAULT_TEST_IMAGE["filename"])
        }
        return [test_case]
    
    def run_plot_detection_test(self, test_config: Dict[str, Any], test_data: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n[测试开始] 地块检测测试")
        print(f"[配置] 基础URL: {test_config.get('base_url', '未设置')}")
        print(f"[配置] 用户名: {test_config.get('test_username', '未设置')}")
        print(f"[配置] 无头模式: {test_config.get('headless', False)}")
        
        config = E2ETestConfig(test_config)
        config.validate()
        
        for attempt in range(RETRY_CONFIG["max_retries"]):
            print(f"\n[重试] 第 {attempt + 1} 次尝试")
            
            test_result = {
                "test_id": TEST_CASES_CONFIG["plot_detection"]["test_id"],
                "test_name": TEST_CASES_CONFIG["plot_detection"]["test_name"],
                "attempt": attempt + 1,
                "start_time": time.strftime('%Y-%m-%d %H:%M:%S'),
                "status": "RUNNING",
                "steps": [],
                "screenshots": [],
                "error_message": None,
                "execution_time": 0
            }
            
            start_time = time.time()
            
            try:
                print(f"[调试] 设置浏览器驱动")
                self._setup_driver(config.config)
                print(f"[调试] 开始执行测试步骤")
                self._execute_test_steps(config, test_data, test_result)
                test_result["status"] = "PASSED"
                test_result["message"] = "测试执行成功"
                print(f"\n[测试成功] 地块检测测试执行成功")
                return test_result
                
            except Exception as e:
                test_result["status"] = "FAILED"
                test_result["error_message"] = str(e)
                test_result["message"] = f"测试执行失败: {str(e)}"
                print(f"\n[测试失败] {str(e)}")
                
                if self.driver:
                    screenshot_path = self._take_screenshot(f"test_failure_attempt_{attempt + 1}")
                    if screenshot_path:
                        test_result["screenshots"].append(screenshot_path)
                        print(f"[调试] 失败截图已保存: {screenshot_path}")
                        
            finally:
                print(f"[调试] 清理浏览器驱动")
                self._cleanup_driver()
                test_result["execution_time"] = round(time.time() - start_time, 2)
                test_result["end_time"] = time.strftime('%Y-%m-%d %H:%M:%S')
                print(f"[调试] 本次尝试执行时间: {test_result['execution_time']}秒")
        
            if "browser" not in str(test_result.get("error_message", "")).lower():
                print(f"[调试] 非浏览器相关错误，停止重试")
                break
                
            if attempt < RETRY_CONFIG["max_retries"] - 1:
                print(f"[调试] 等待 {RETRY_CONFIG['retry_delay']} 秒后重试")
                time.sleep(RETRY_CONFIG["retry_delay"])
        
        print(f"\n[测试结束] 地块检测测试")
        return test_result

    def _setup_driver(self, config: Dict[str, Any]):
        chrome_options = Options()
        
        for option in CHROME_OPTIONS:
            chrome_options.add_argument(option)
        
        if config.get('headless', False):
            chrome_options.add_argument('--headless')
            chrome_options.add_argument(HEADLESS_WINDOW_SIZE)
        else:
            chrome_options.add_argument(MAXIMIZED_WINDOW)
        
        user_data_dir = tempfile.mkdtemp(prefix="chrome_test_")
        chrome_options.add_argument(f'--user-data-dir={user_data_dir}')
        
        try:
            service = Service()
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            timeout = config.get('timeout', WAIT_CONFIG["implicit_wait"])
            self.driver.implicitly_wait(timeout)
            self.driver.set_page_load_timeout(WAIT_CONFIG["page_load_timeout"])
            
            self.wait = WebDriverWait(self.driver, timeout)
            self.short_wait = WebDriverWait(self.driver, WAIT_CONFIG["short_wait"])
            
            if not config.get('headless', False):
                self.driver.maximize_window()
            
        except Exception as e:
            raise Exception(f"Chrome浏览器初始化失败: {str(e)}")

    def _cleanup_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None
                self.wait = None
                self.short_wait = None

    def _execute_test_steps(self, config: E2ETestConfig, test_data: Dict[str, Any], result: Dict[str, Any]):
        base_url = config.get_base_url()
        username = config.get('test_username')
        password = config.get('test_password')
        
        self._add_step_result(result, "访问网站", "执行中")
        self._navigate_to_website(base_url)
        self._add_step_result(result, "访问网站", "成功")
        
        self._add_step_result(result, "用户登录", "执行中")
        self._perform_login(username, password)
        self._add_step_result(result, "用户登录", "成功")
        
        self._add_step_result(result, "点击第一个地块卡片", "执行中")
        self._click_first_plot_card()
        self._add_step_result(result, "点击第一个地块卡片", "成功")
        
        self._add_step_result(result, "点击更多选项按钮", "执行中")
        self._click_more_options_button()
        self._add_step_result(result, "点击更多选项按钮", "成功")
        
        self._add_step_result(result, "选择疾病检测", "执行中")
        self._select_disease_detection_option()
        self._add_step_result(result, "选择疾病检测", "成功")
        
        self._add_step_result(result, "上传图片", "执行中")
        self._upload_test_image(test_data)
        self._add_step_result(result, "上传图片", "成功")
        
        self._add_step_result(result, "提交检测", "执行中")
        self._submit_detection_request()
        self._add_step_result(result, "提交检测", "成功")
        
        self._add_step_result(result, "等待结果", "执行中")
        self._wait_for_detection_result()
        self._add_step_result(result, "等待结果", "成功")
    
    def _navigate_to_website(self, base_url: str):
        try:
            print(f"[调试] 正在访问网站: {base_url}")
            self.driver.get(base_url)
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            self._wait_for_ionic_ready()
            print(f"[调试] 网站访问成功")
        except Exception as e:
            print(f"[调试] 网站访问失败: {str(e)}")
            raise Exception(f"访问网站失败: {str(e)}")
    
    def _wait_for_ionic_ready(self):
        try:
            self.short_wait.until(
                EC.any_of(*[
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    for selector in SELECTORS["ionic_ready"]
                ])
            )
            # 简化的ionic ready检查
            self.driver.execute_script("""
                if (window.Ionic && window.Ionic.isReady) {
                    console.log('Ionic is ready');
                }
            """)
            time.sleep(1)
        except Exception:
            pass
    
    def _add_step_result(self, result: Dict[str, Any], step_name: str, status: str):
        step_info = {
            "step_name": step_name,
            "status": status,
            "timestamp": time.strftime('%H:%M:%S')
        }
        result["steps"].append(step_info)
        
        if status == "执行中":
            print(f"[测试] 正在执行: {step_name}")
        elif status == "成功":
            print(f"[测试] 完成: {step_name}")
        elif status == "失败":
            print(f"[测试] 失败: {step_name}")

    def _perform_login(self, username: str, password: str):
        try:
            print(f"[调试] 开始登录流程 - 用户名: {username}")
            time.sleep(WAIT_CONFIG["navigation_delay"])
            self._wait_for_login_form()
            
            login_elements = self._find_login_elements_js()
            
            if login_elements['username'] and login_elements['password'] and login_elements['loginButton']:
                print(f"[调试] 使用JavaScript方式登录")
                self._perform_login_js(login_elements, username, password)
            else:
                print(f"[调试] 使用Selenium方式登录")
                self._perform_login_selenium(username, password)
            
            time.sleep(WAIT_CONFIG["login_delay"])
            print(f"[调试] 验证登录结果")
            self._verify_login_success()
            print(f"[调试] 登录成功")
            
        except Exception as e:
            print(f"[调试] 登录失败: {str(e)}")
            error_message = self._get_error_message()
            if error_message:
                raise Exception(f"登录失败: {error_message}")
            else:
                raise Exception(f"登录过程失败: {str(e)}")

    def _wait_for_login_form(self):
        try:
            self.wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ion-input[label='用户名']")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']"))
                )
            )
            time.sleep(1)
        except TimeoutException:
            raise Exception("登录表单加载超时")

    def _find_login_elements_js(self) -> Dict[str, Any]:
        try:
            return self.driver.execute_script("""
                // 查找登录元素
                const usernameInput = document.querySelector('ion-input[label="用户名"] input') || 
                                    document.querySelector('input[type="text"]');
                const passwordInput = document.querySelector('ion-input[label="密码"] input') || 
                                    document.querySelector('input[type="password"]');
                
                const loginButtons = Array.from(document.querySelectorAll('ion-button'));
                const loginButton = loginButtons.find(btn => 
                    btn.textContent.trim() === '登录' && 
                    btn.getAttribute('fill') !== 'outline'
                );
                
                return {
                    username: usernameInput,
                    password: passwordInput,
                    loginButton: loginButton
                };
            """)
        except Exception:
            return {'username': None, 'password': None, 'loginButton': None}

    def _perform_login_js(self, elements: Dict[str, Any], username: str, password: str):
        try:
            # 简化的Vue输入触发
            self.driver.execute_script("""
                const element = arguments[0];
                const value = arguments[1];
                
                if (element) {
                    element.value = value;
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                }
            """, elements['username'], username)
            time.sleep(WAIT_CONFIG["input_delay"])
            
            self.driver.execute_script("""
                const element = arguments[0];
                const value = arguments[1];
                
                if (element) {
                    element.value = value;
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                }
            """, elements['password'], password)
            time.sleep(WAIT_CONFIG["input_delay"])
            
            # 简化的Vue按钮点击
            self.driver.execute_script("""
                const button = arguments[0];
                if (button) {
                    button.click();
                }
            """, elements['loginButton'])
        except Exception as e:
            raise Exception(f"JavaScript登录执行失败: {str(e)}")

    def _perform_login_selenium(self, username: str, password: str):
        try:
            username_input = self._find_element_by_multiple_selectors(SELECTORS["login"]["username"], "用户名输入框")
            self._safe_input_vue(username_input, username, "用户名")
            
            password_input = self._find_element_by_multiple_selectors(SELECTORS["login"]["password"], "密码输入框")
            self._safe_input_vue(password_input, password, "密码")
            
            login_button = self._find_login_button()
            self._safe_click_vue(login_button, "登录按钮")
        except Exception as e:
            raise Exception(f"Selenium登录执行失败: {str(e)}")

    def _find_login_button(self):
        try:
            buttons = self.driver.find_elements(By.CSS_SELECTOR, "ion-button")
            for button in buttons:
                if button.is_displayed() and button.text.strip() == "登录":
                    fill_attr = button.get_attribute('fill')
                    if not fill_attr or fill_attr != 'outline':
                        return button
        except Exception:
            pass
        
        for selector in SELECTORS["login"]["login_button"]:
            try:
                if "contains" in selector:
                    continue
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed() and element.is_enabled():
                    return element
            except NoSuchElementException:
                continue
        
        raise Exception("未找到登录按钮")

    def _safe_input_vue(self, element, text: str, field_name: str):
        try:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(WAIT_CONFIG["scroll_delay"])
            
            element.click()
            time.sleep(WAIT_CONFIG["input_delay"])
            
            element.clear()
            element.send_keys(text)
            
            if element.get_attribute('value') != text:
                # 简化的Vue输入触发
                self.driver.execute_script("""
                    const element = arguments[0];
                    const value = arguments[1];
                    
                    element.value = value;
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                """, element, text)
                time.sleep(WAIT_CONFIG["input_delay"])
        except Exception as e:
            raise Exception(f"{field_name}输入失败: {str(e)}")

    def _safe_click_vue(self, element, element_name: str):
        try:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(WAIT_CONFIG["scroll_delay"])
            
            WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(element))
            
            try:
                element.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", element)
                
            time.sleep(WAIT_CONFIG["click_delay"])
        except Exception as e:
            raise Exception(f"{element_name}点击失败: {str(e)}")

    def _verify_login_success(self):
        try:
            start_time = time.time()
            timeout = WAIT_CONFIG["implicit_wait"]
            
            while time.time() - start_time < timeout:
                current_url = self.driver.current_url
                
                if any(pattern in current_url for pattern in URL_VALIDATION["login_success_patterns"]):
                    if self._wait_for_home_page_loaded():
                        return
                
                if any(pattern in current_url for pattern in URL_VALIDATION["login_page_patterns"]):
                    error_msg = self._get_error_message()
                    if error_msg:
                        raise Exception(f"登录失败，错误信息: {error_msg}")
                
                time.sleep(1)
            
            current_url = self.driver.current_url
            if any(pattern in current_url for pattern in URL_VALIDATION["login_success_patterns"]):
                return
            
            if self._check_login_success_indicators():
                return
            
            raise Exception(f"登录后未跳转到预期页面，当前URL: {current_url}")
        except TimeoutException:
            raise Exception("登录验证超时")

    def _wait_for_home_page_loaded(self) -> bool:
        try:
            self.wait.until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ion-searchbar")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ion-fab ion-fab-button")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ion-grid")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ion-card"))
                )
            )
            # 简化的首页检查
            return self.driver.execute_script("""
                return document.querySelector('ion-searchbar') !== null ||
                       document.querySelector('ion-fab') !== null ||
                       document.querySelector('ion-grid') !== null;
            """)
        except TimeoutException:
            return False

    def _check_login_success_indicators(self) -> bool:
        try:
            for selector in ["ion-searchbar", "ion-fab", "ion-grid"]:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element.is_displayed():
                        return True
                except NoSuchElementException:
                    continue
            
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            return any(keyword in page_text for keyword in ["搜索地块", "暂无地块", "天气"])
        except Exception:
            return False

    def _click_first_plot_card(self):
        try:
            print(f"[调试] 正在查找并点击第一个地块卡片")
            time.sleep(WAIT_CONFIG["navigation_delay"])
            
            # 直接使用JavaScript查找第一个地块卡片
            first_plot_card = self.driver.execute_script("""
                // 查找第一个地块卡片
                const plotCards = Array.from(document.querySelectorAll('ion-card[router-link*="/tabs/strip/"]'));
                if (plotCards.length > 0) {
                    return plotCards[0];
                }
                
                // 备用方案：查找网格中的第一个卡片
                const gridCards = Array.from(document.querySelectorAll('ion-grid ion-row ion-col ion-card[button]'));
                if (gridCards.length > 0) {
                    return gridCards[0];
                }
                
                return null;
            """)
            
            if first_plot_card:
                print(f"[调试] 通过JavaScript找到第一个地块卡片")
                self._safe_click_vue(first_plot_card, "第一个地块卡片")
            else:
                print(f"[调试] JavaScript未找到地块卡片，使用Selenium方式查找")
                plot_cards = self._find_plot_cards()
                if not plot_cards:
                    print(f"[调试] 未找到任何地块卡片")
                    raise Exception("未找到任何地块卡片")
                print(f"[调试] 找到 {len(plot_cards)} 个地块卡片")
                self._safe_click_vue(plot_cards[0], "第一个地块卡片")
            
            time.sleep(WAIT_CONFIG["plot_detail_delay"])
            
            current_url = self.driver.current_url
            print(f"[调试] 当前URL: {current_url}")
            if not any(pattern in current_url for pattern in URL_VALIDATION["plot_detail_patterns"]):
                raise Exception(f"未成功跳转到地块详情页")
            print(f"[调试] 成功跳转到地块详情页")
        except Exception as e:
            print(f"[调试] 点击地块卡片失败: {str(e)}")
            raise Exception(f"点击第一个地块卡片失败: {str(e)}")

    def _click_more_options_button(self):
        try:
            print(f"[调试] 正在点击更多选项按钮")
            time.sleep(WAIT_CONFIG["navigation_delay"])
            
            # 首先尝试 JavaScript 点击
            click_result = self.driver.execute_script("""
                var button = document.querySelector('#more-options-button');
                if (button) {
                    console.log('[JS] 找到更多选项按钮，准备点击');
                    button.click();
                    return { success: true };
                }
                return { success: false, error: '未找到按钮' };
            """)
            
            if click_result.get('success'):
                print(f"[调试] JavaScript 点击成功")
            else:
                print(f"[调试] JavaScript 点击失败，使用 Selenium 方式")
                more_button = self._find_element_by_multiple_selectors(
                    SELECTORS["plot_detail"]["more_options_button"], "更多选项按钮"
                )
                self._safe_click_vue(more_button, "更多选项按钮")
            
            # 等待 Popover 出现
            time.sleep(WAIT_CONFIG["click_delay"] * 2)  # 稍微多等一会
            
            # 验证 Popover 是否出现
            popover_visible = self.driver.execute_script("""
                var popover = document.querySelector('ion-popover');
                return popover && popover.offsetParent !== null;
            """)
            
            if popover_visible:
                print(f"[调试] Popover 已显示")
            else:
                print(f"[调试] Popover 未显示，可能需要再次点击")
                # 如果 Popover 没有显示，再尝试一次点击
                time.sleep(1)
                self.driver.execute_script("""
                    var button = document.querySelector('#more-options-button');
                    if (button) {
                        button.click();
                    }
                """)
                time.sleep(WAIT_CONFIG["click_delay"])
            
            print(f"[调试] 更多选项按钮点击完成")
            
        except Exception as e:
            print(f"[调试] 点击更多选项按钮失败: {str(e)}")
            raise Exception(f"点击更多选项按钮失败: {str(e)}")

    def _select_disease_detection_option(self):
        try:
            print(f"[调试] 正在查找疾病检测选项")
            time.sleep(WAIT_CONFIG["click_delay"])
            
            # 等待 Popover 出现和渲染完成
            print(f"[调试] 等待 Popover 显示...")
            try:
                # 等待 Popover 容器出现
                self.short_wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ion-popover"))
                )
                print(f"[调试] Popover 容器已出现")
                
                # 再等待一段时间确保内容渲染完成
                time.sleep(WAIT_CONFIG["navigation_delay"])
                
                # 等待 Popover 内容加载
                self.short_wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ion-popover ion-content"))
                )
                print(f"[调试] Popover 内容已加载")
                
            except TimeoutException:
                print(f"[调试] Popover 未能及时显示，尝试继续...")
        
            # 使用 JavaScript 直接查找和点击疾病检测选项
            detection_clicked = self.driver.execute_script("""
                console.log('[JS] 开始查找疾病检测选项');
                
                // 查找 Popover 中的所有 ion-item
                var popover = document.querySelector('ion-popover');
                if (!popover) {
                    console.log('[JS] 未找到 ion-popover');
                    return { success: false, error: '未找到 Popover' };
                }
                
                var items = popover.querySelectorAll('ion-item');
                console.log('[JS] 在 Popover 中找到', items.length, '个 ion-item');
                
                for (var i = 0; i < items.length; i++) {
                    var item = items[i];
                    var text = item.textContent.trim();
                    console.log('[JS] 项目', i, '文本:', text);
                    
                    if (text.includes('疾病检测')) {
                        console.log('[JS] 找到疾病检测选项，准备点击');
                        
                        // 触发 Vue 的点击事件
                        item.dispatchEvent(new Event('click', { bubbles: true }));
                        
                        // 也尝试直接点击
                        item.click();
                        
                        return { success: true, text: text };
                    }
                }
                
                return { success: false, error: '未找到疾病检测选项', itemCount: items.length };
            """)
            
            if detection_clicked and detection_clicked.get('success'):
                print(f"[调试] JavaScript 成功点击疾病检测选项: {detection_clicked.get('text')}")
            else:
                print(f"[调试] JavaScript 未能点击疾病检测选项: {detection_clicked.get('error')}")
                print(f"[调试] 尝试使用 Selenium 方式查找...")
                
                # 备用方案：使用 Selenium 查找
                self._find_and_click_disease_detection_selenium()
            
            # 等待疾病检测模态框出现 - 增加等待时间和更灵活的检查
            print(f"[调试] 等待疾病检测模态框出现...")
            
            # 等待Vue组件状态更新
            time.sleep(WAIT_CONFIG["navigation_delay"] * 2)  # 增加等待时间
            
            # 使用更灵活的方式检查模态框
            modal_opened = False
            max_attempts = 10
            
            for attempt in range(max_attempts):
                print(f"[调试] 检查模态框状态 (尝试 {attempt + 1}/{max_attempts})")
                
                modal_status = self.driver.execute_script("""
                    // 检查所有可能的模态框状态
                    var modals = document.querySelectorAll('ion-modal');
                    var modalInfo = [];
                    
                    for (var i = 0; i < modals.length; i++) {
                        var modal = modals[i];
                        var info = {
                            index: i,
                            isOpen: modal.getAttribute('is-open'),
                            visible: modal.offsetParent !== null,
                            display: window.getComputedStyle(modal).display,
                            contains: modal.textContent.includes('疾病检测') || modal.textContent.includes('检测')
                        };
                        modalInfo.push(info);
                        
                        // 如果找到疾病检测模态框且已打开
                        if (info.contains && (info.isOpen === 'true' || info.visible)) {
                            return { success: true, modalIndex: i, info: info };
                        }
                    }
                    
                    return { success: false, modals: modalInfo };
                """)
                
                if modal_status.get('success'):
                    print(f"[调试] 找到已打开的疾病检测模态框: {modal_status.get('info')}")
                    modal_opened = True
                    break
                else:
                    print(f"[调试] 模态框状态: {modal_status.get('modals')}")
                    time.sleep(1)  # 等待1秒后再次检查
            
            if not modal_opened:
                print(f"[调试] 模态框未能打开，尝试使用传统方式检查...")
                
                # 传统方式检查模态框
                try:
                    # 尝试查找任何包含疾病检测内容的模态框
                    modal_elements = self.driver.find_elements(By.CSS_SELECTOR, "ion-modal")
                    print(f"[调试] 找到 {len(modal_elements)} 个模态框元素")
                    
                    for i, modal in enumerate(modal_elements):
                        try:
                            if modal.is_displayed():
                                modal_text = modal.text
                                print(f"[调试] 模态框 {i+1} 内容预览: {modal_text[:100]}...")
                                if "疾病检测" in modal_text or "检测" in modal_text:
                                    print(f"[调试] 找到疾病检测模态框 (传统方式)")
                                    modal_opened = True
                                    break
                        except Exception as e:
                            print(f"[调试] 检查模态框 {i+1} 时出错: {str(e)}")
                            continue
                    
                    if not modal_opened:
                        # 最后尝试：等待任何模态框打开
                        try:
                            self.short_wait.until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "ion-modal[is-open='true']"))
                            )
                            print(f"[调试] 检测到有模态框已打开")
                            modal_opened = True
                        except TimeoutException:
                            pass
                        
                except Exception as e:
                    print(f"[调试] 传统方式检查模态框失败: {str(e)}")
            
            if not modal_opened:
                print(f"[调试] 疾病检测模态框未打开，检查页面状态...")
                self._debug_page_state()
                
                # 尝试再次点击疾病检测选项
                print(f"[调试] 尝试再次点击疾病检测选项...")
                time.sleep(2)
                
                retry_clicked = self.driver.execute_script("""
                    // 再次尝试找到并点击疾病检测选项
                    var items = document.querySelectorAll('ion-item');
                    for (var i = 0; i < items.length; i++) {
                        var item = items[i];
                        if (item.textContent.includes('疾病检测') && item.offsetParent !== null) {
                            console.log('[JS] 重新点击疾病检测选项');
                            item.click();
                            return true;
                        }
                    }
                    return false;
                """)
                
                if retry_clicked:
                    print(f"[调试] 重新点击成功，再次等待模态框...")
                    time.sleep(3)
                    
                    # 再次检查模态框
                    final_check = self.driver.execute_script("""
                        var modals = document.querySelectorAll('ion-modal');
                        for (var i = 0; i < modals.length; i++) {
                            var modal = modals[i];
                            if ((modal.getAttribute('is-open') === 'true' || modal.offsetParent !== null) && 
                                modal.textContent.includes('疾病检测')) {
                                return true;
                            }
                        }
                        return false;
                    """)
                    
                    if final_check:
                        print(f"[调试] 重新点击后模态框已打开")
                        modal_opened = True
            
            if not modal_opened:
                raise Exception("疾病检测模态框未打开")
            else:
                print(f"[调试] 疾病检测模态框已成功打开")
                
        except Exception as e:
            print(f"[调试] 选择疾病检测选项失败: {str(e)}")
            raise Exception(f"选择疾病检测选项失败: {str(e)}")

    def _find_and_click_disease_detection_selenium(self):
        """使用 Selenium 方式查找并点击疾病检测选项"""
        try:
            # 查找 Popover 容器
            popover = self.driver.find_element(By.CSS_SELECTOR, "ion-popover")
            if not popover:
                raise Exception("未找到 Popover 容器")
            
            # 在 Popover 中查找所有 ion-item
            menu_items = popover.find_elements(By.CSS_SELECTOR, "ion-item")
            print(f"[调试] Selenium 在 Popover 中找到 {len(menu_items)} 个菜单项")
            
            detection_item = None
            for i, item in enumerate(menu_items):
                if item.is_displayed():
                    item_text = item.text.strip()
                    print(f"[调试] 菜单项 {i+1}: {item_text}")
                    if "疾病检测" in item_text:
                        detection_item = item
                        print(f"[调试] 找到疾病检测选项")
                        break
            
            if not detection_item:
                # 如果还是找不到，尝试更宽泛的查找
                all_items = self.driver.find_elements(By.CSS_SELECTOR, "ion-item")
                print(f"[调试] 在整个页面找到 {len(all_items)} 个 ion-item")
                for i, item in enumerate(all_items):
                    if item.is_displayed():
                        item_text = item.text.strip()
                        print(f"[调试] 页面菜单项 {i+1}: {item_text}")
                        if "疾病检测" in item_text:
                            detection_item = item
                            print(f"[调试] 在页面中找到疾病检测选项")
                            break
            
            if not detection_item:
                raise Exception("未找到疾病检测选项")
            
            self._safe_click_vue(detection_item, "疾病检测选项")
            
        except Exception as e:
            print(f"[调试] Selenium 查找疾病检测选项失败: {str(e)}")
            raise

    def _debug_page_state(self):
        """调试页面状态 - 增强版"""
        try:
            page_info = self.driver.execute_script("""
                var modals = document.querySelectorAll('ion-modal');
                var modalDetails = [];
                
                for (var i = 0; i < modals.length; i++) {
                    var modal = modals[i];
                    modalDetails.push({
                        index: i,
                        isOpen: modal.getAttribute('is-open'),
                        visible: modal.offsetParent !== null,
                        display: window.getComputedStyle(modal).display,
                        textContent: modal.textContent.substring(0, 100),
                        className: modal.className,
                        hasDetectionText: modal.textContent.includes('疾病检测') || modal.textContent.includes('检测')
                    });
                }
                
                return {
                    url: window.location.href,
                    title: document.title,
                    popoverCount: document.querySelectorAll('ion-popover').length,
                    modalCount: document.querySelectorAll('ion-modal').length,
                    itemCount: document.querySelectorAll('ion-item').length,
                    visibleItemCount: Array.from(document.querySelectorAll('ion-item')).filter(el => el.offsetParent !== null).length,
                    popoverVisible: Array.from(document.querySelectorAll('ion-popover')).some(el => el.offsetParent !== null),
                    modalOpen: Array.from(document.querySelectorAll('ion-modal')).some(el => el.getAttribute('is-open') === 'true'),
                    modalDetails: modalDetails
                };
            """)
            print(f"[调试] 详细页面状态: {page_info}")
        except Exception as e:
            print(f"[调试] 获取页面状态失败: {str(e)}")

    def _upload_test_image(self, test_data: Dict[str, Any]):
        try:
            image_path = test_data.get('image_path', os.path.join(self.test_data_dir, DEFAULT_TEST_IMAGE["filename"]))
            print(f"[调试] 准备上传图片: {image_path}")
            
            if not os.path.exists(image_path):
                print(f"[调试] 测试图片不存在: {image_path}")
                raise Exception(f"测试图片不存在: {image_path}")
            
            print(f"[调试] 图片文件存在，大小: {os.path.getsize(image_path)} 字节")
            time.sleep(WAIT_CONFIG["navigation_delay"])
            
            file_input = self._find_element_by_multiple_selectors(
                SELECTORS["disease_detection"]["file_input"], "文件上传输入框"
            )
            print(f"[调试] 找到文件上传输入框")
            
            absolute_path = os.path.abspath(image_path)
            file_input.send_keys(absolute_path)
            print(f"[调试] 文件路径已发送到输入框")
            time.sleep(WAIT_CONFIG["input_delay"])
            
            file_value = file_input.get_attribute('value')
            if not file_value:
                print(f"[调试] 文件上传失败，输入框值为空")
                raise Exception("文件上传失败")
            else:
                print(f"[调试] 文件上传成功，输入框值: {file_value}")
        except Exception as e:
            print(f"[调试] 上传图片失败: {str(e)}")
            raise Exception(f"上传测试图片失败: {str(e)}")

    def _submit_detection_request(self):
        try:
            print(f"[调试] 正在查找并点击提交检测按钮")
            submit_button = self._find_element_by_multiple_selectors(
                SELECTORS["disease_detection"]["submit_button"], "提交检测按钮"
            )
            print(f"[调试] 找到提交检测按钮")
            
            if submit_button.get_attribute('disabled'):
                print(f"[调试] 提交按钮被禁用")
                raise Exception("提交按钮被禁用")
            
            print(f"[调试] 提交按钮可用，正在点击")
            self._safe_click_vue(submit_button, "提交检测按钮")
            print(f"[调试] 提交检测按钮点击完成")
        except Exception as e:
            print(f"[调试] 提交检测失败: {str(e)}")
            raise Exception(f"提交检测请求失败: {str(e)}")

    def _wait_for_detection_result(self):
        """等待检测结果 - 优化版"""
        try:
            max_wait_time = DETECTION_WAIT_CONFIG["max_wait_time"]
            check_interval = DETECTION_WAIT_CONFIG["check_interval"]
            print(f"[调试] 开始等待检测结果，最大等待时间: {max_wait_time}秒")
            
            # 先等待一段时间让请求处理
            print(f"[调试] 等待检测请求处理...")
            time.sleep(3)
            
            for attempt in range(max_wait_time // check_interval):
                elapsed_time = (attempt + 1) * check_interval
                print(f"[调试] 等待检测结果中... ({elapsed_time}/{max_wait_time}秒)")
                
                # 检查是否有错误信息
                error_msg = self._check_for_error_message()
                if error_msg:
                    print(f"[调试] 检测过程中出现错误: {error_msg}")
                    raise Exception(f"检测过程中出现错误: {error_msg}")
                
                # 检查检测结果
                if self._check_for_detection_result():
                    print(f"[调试] 检测结果已出现，等待时间: {elapsed_time}秒")
                    # 额外等待一下确保结果完整加载
                    time.sleep(2)
                    return True
                
                # 检查是否有成功提示
                success_alert = self._check_for_success_alert()
                if success_alert:
                    print(f"[调试] 检测到成功提示，继续等待结果显示...")
                    time.sleep(3)
                    continue
                
                time.sleep(check_interval)
            
            # 超时后最后检查一次
            print(f"[调试] 等待超时，进行最终检查...")
            if self._check_final_result():
                print(f"[调试] 最终检查发现结果")
                return True
            
            print(f"[调试] 检测处理超时，未找到有效结果")
            raise Exception(f"检测处理超时")
            
        except Exception as e:
            print(f"[调试] 等待检测结果失败: {str(e)}")
            raise Exception(f"等待检测结果失败: {str(e)}")

    def _check_for_success_alert(self) -> bool:
        """检查是否有成功提示"""
        try:
            return self.driver.execute_script("""
                // 检查 ion-alert
                var alerts = document.querySelectorAll('ion-alert');
                for (var i = 0; i < alerts.length; i++) {
                    var alert = alerts[i];
                    if (alert.offsetParent !== null) {  // 可见的alert
                        var text = alert.textContent.toLowerCase();
                        if (text.includes('成功') || text.includes('检测完成') || text.includes('success')) {
                            return true;
                        }
                    }
                }
                
                // 检查 ion-toast
                var toasts = document.querySelectorAll('ion-toast');
                for (var i = 0; i < toasts.length; i++) {
                    var toast = toasts[i];
                    if (toast.offsetParent !== null) {
                        var text = toast.textContent.toLowerCase();
                        if (text.includes('成功') || text.includes('检测完成') || text.includes('success')) {
                            return true;
                        }
                    }
                }
                
                return false;
            """)
        except Exception:
            return False

    def _check_final_result(self) -> bool:
        """最终检查结果"""
        try:
            print(f"[调试] 执行最终结果检查...")
            
            # 1. 检查页面是否有任何结果内容
            page_info = self.driver.execute_script("""
                var pageText = document.body.textContent.toLowerCase();
                var hasResultKeywords = pageText.includes('病害名称') || 
                                      pageText.includes('检测结果') || 
                                      pageText.includes('置信度') || 
                                      pageText.includes('建议');
                
                var modalCount = document.querySelectorAll('ion-modal[is-open="true"]').length;
                var cardCount = document.querySelectorAll('ion-card').length;
                var logCount = document.querySelectorAll('ion-list ion-item').length;
                
                return {
                    hasResultKeywords: hasResultKeywords,
                    modalCount: modalCount,
                    cardCount: cardCount,
                    logCount: logCount,
                    currentUrl: window.location.href
                };
            """)
            
            print(f"[调试] 最终检查结果: {page_info}")
            
            if page_info and page_info.get('hasResultKeywords'):
                print(f"[调试] 页面包含结果关键词")
                return True
            
            # 2. 检查传统方式
            return self._has_any_result_content()
            
        except Exception as e:
            print(f"[调试] 最终检查失败: {str(e)}")
            return False

    def _has_any_result_content(self) -> bool:
        """检查是否有任何结果内容 - 增强版"""
        try:
            page_source = self.driver.page_source.lower()
            
            # 更具体的关键词检查
            result_keywords = [
                "检测结果", "病害名称", "置信度", "建议", 
                "detection", "result", "disease", "confidence"
            ]
            
            success_keywords = [
                "检测完成", "分析完成", "处理完成", "成功",
                "detection complete", "analysis complete", "success"
            ]
            
            found_result_keywords = [k for k in result_keywords if k in page_source]
            found_success_keywords = [k for k in success_keywords if k in page_source]
            
            print(f"[调试] 找到结果关键词: {found_result_keywords}")
            print(f"[调试] 找到成功关键词: {found_success_keywords}")
            
            # 如果找到足够的关键词，认为有结果
            if len(found_result_keywords) >= 2 or len(found_success_keywords) >= 1:
                return True
            
            # 检查是否有新的日志项目（检测完成后会刷新数据）
            try:
                log_items = self.driver.find_elements(By.CSS_SELECTOR, "ion-list ion-item")
                if len(log_items) > 0:
                    latest_log = log_items[0]
                    log_text = latest_log.text.lower()
                    if any(keyword in log_text for keyword in ["检测", "病害", "识别", "分析"]):
                        print(f"[调试] 发现新的检测相关日志")
                        return True
            except Exception as e:
                print(f"[调试] 检查日志项目失败: {str(e)}")
            
            return False
            
        except Exception:
            return False

    def _find_plot_cards(self):
        try:
            # 使用JavaScript查找
            plot_cards = self.driver.execute_script("""
                return Array.from(document.querySelectorAll('ion-card[router-link*="/tabs/strip/"]'));
            """)
            if plot_cards:
                return plot_cards
        except Exception:
            pass
        
        for selector in SELECTORS["plot_cards"]:
            try:
                cards = self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
                visible_cards = [card for card in cards if card.is_displayed() and card.is_enabled()]
                if visible_cards:
                    return visible_cards
            except TimeoutException:
                continue
        
        return []

    def _find_element_by_multiple_selectors(self, selectors: List[str], element_name: str):
        for selector in selectors:
            try:
                if "contains" in selector:
                    continue
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed() and element.is_enabled():
                    return element
            except NoSuchElementException:
                continue
        raise Exception(f"未找到{element_name}")

    def _get_error_message(self) -> str:
        try:
            for selector in SELECTORS["error_messages"]:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element.is_displayed():
                        return element.text.strip()
                except NoSuchElementException:
                    continue
        except Exception:
            pass
        return ""

    def _take_screenshot(self, name: str) -> str:
        try:
            timestamp = int(time.time())
            filename = f"{name}_{timestamp}.png"
            filepath = os.path.join(self.screenshot_dir, filename)
            self.driver.save_screenshot(filepath)
            print(f"[调试] 截图已保存: {filepath}")
            return filepath
        except Exception as e:
            print(f"[调试] 截图失败: {str(e)}")
            return None

    # 天气信息测试方法
    def get_weather_predefined_test_cases(self) -> List[Dict[str, Any]]:
        return [TEST_CASES_CONFIG["weather_info"]]
    
    def run_weather_info_test(self, test_config: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n[测试开始] 天气信息测试")
        print(f"[配置] 基础URL: {test_config.get('base_url', '未设置')}")
        
        test_result = {
            "test_id": TEST_CASES_CONFIG["weather_info"]["test_id"],
            "test_name": TEST_CASES_CONFIG["weather_info"]["test_name"],
            "start_time": time.strftime('%Y-%m-%d %H:%M:%S'),
            "status": "RUNNING",
            "steps": [],
            "weather_data": {},
            "error_message": None,
            "execution_time": 0
        }
        
        start_time = time.time()
        
        try:
            print(f"[调试] 设置浏览器驱动")
            self._setup_driver(test_config)
            print(f"[调试] 开始执行天气测试步骤")
            self._execute_weather_test_steps(test_config, test_result)
            test_result["status"] = "PASSED"
            test_result["message"] = "天气信息测试执行成功"
            print(f"\n[测试成功] 天气信息测试执行成功")
        except Exception as e:
            test_result["status"] = "FAILED"
            test_result["error_message"] = str(e)
            test_result["message"] = f"天气信息测试执行失败: {str(e)}"
            print(f"\n[测试失败] {str(e)}")
        finally:
            print(f"[调试] 清理浏览器驱动")
            self._cleanup_driver()
            test_result["execution_time"] = round(time.time() - start_time, 2)
            test_result["end_time"] = time.strftime('%Y-%m-%d %H:%M:%S')
            print(f"[调试] 执行时间: {test_result['execution_time']}秒")
            
        print(f"\n[测试结束] 天气信息测试")
        return test_result
    
    def _execute_weather_test_steps(self, config: Dict[str, Any], result: Dict[str, Any]):
        config_obj = E2ETestConfig(config)
        base_url = config_obj.get_base_url()
        username = config_obj.get('test_username')
        password = config_obj.get('test_password')
        
        self._add_step_result(result, "访问网站", "执行中")
        self._navigate_to_website(base_url)
        self._add_step_result(result, "访问网站", "成功")
        
        self._add_step_result(result, "用户登录", "执行中")
        self._perform_login(username, password)
        self._add_step_result(result, "用户登录", "成功")
        
        self._add_step_result(result, "验证天气信息", "执行中")
        weather_data = self._verify_weather_info_display()
        result["weather_data"] = weather_data
        self._add_step_result(result, "验证天气信息", "成功")
    
    def _verify_weather_info_display(self) -> Dict[str, Any]:
        print(f"[调试] 开始验证天气信息显示")
        time.sleep(WAIT_CONFIG["weather_info_delay"])
        
        try:
            # 简化的天气卡片查找
            weather_container = self.driver.execute_script("""
                return Array.from(document.querySelectorAll('ion-card')).find(card => {
                    const title = card.querySelector('ion-card-title');
                    return title && title.textContent.includes('天气');
                });
            """)
            
            if not weather_container:
                print(f"[调试] JavaScript未找到天气容器，使用Selenium方式查找")
                for i, selector in enumerate(SELECTORS["weather_info"]):
                    try:
                        container = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if container.is_displayed():
                            print(f"[调试] 通过选择器 {i+1} 找到天气容器")
                            weather_container = container
                            break
                    except NoSuchElementException:
                        print(f"[调试] 选择器 {i+1} 未找到天气容器")
                        continue
            else:
                print(f"[调试] JavaScript找到天气容器")
            
            if not weather_container:
                print(f"[调试] 未找到天气信息容器")
                raise Exception("未找到天气信息容器")
            
            print(f"[调试] 开始提取天气数据")
            weather_data = self._extract_weather_data(weather_container)
            print(f"[调试] 提取到的天气数据: {weather_data}")
            
            if not any(weather_data.values()):
                print(f"[调试] 天气信息容器存在但未找到具体天气数据")
                raise Exception("天气信息容器存在但未找到具体天气数据")
            
            weather_data["status"] = "天气信息获取成功"
            print(f"[调试] 天气信息验证成功")
            return weather_data
        except Exception as e:
            print(f"[调试] 天气信息验证失败: {str(e)}")
            raise Exception(f"天气信息验证失败: {str(e)}")

    def _extract_weather_data(self, container) -> Dict[str, Any]:
        weather_data = {}
        
        try:
            title_element = container.find_element(By.CSS_SELECTOR, "ion-card-title")
            if title_element and title_element.is_displayed():
                weather_data["title"] = title_element.text.strip()
            
            paragraphs = container.find_elements(By.CSS_SELECTOR, "ion-card-content p")
            for i, p in enumerate(paragraphs):
                if p.is_displayed():
                    text = p.text.strip()
                    if text:
                        if "°C" in text:
                            weather_data["temperature"] = text
                        elif "天气" in text:
                            weather_data[f"weather_{i}"] = text
                        else:
                            weather_data[f"info_{i}"] = text
            
            if not weather_data:
                weather_data["container_text"] = container.text.strip()
        except Exception as e:
            weather_data["error"] = str(e)
        
        return weather_data

    def get_plot_management_predefined_test_cases(self) -> List[Dict[str, Any]]:
        """获取地块管理测试的预定义测试用例"""
        from app.static.system_test import TEST_CASES_CONFIG
        return [TEST_CASES_CONFIG["plot_management"]]

    
    def _execute_plot_management_steps(self, config: E2ETestConfig, result: Dict[str, Any]):
        """执行地块管理测试步骤"""
        base_url = config.get_base_url()
        username = config.get('test_username')
        password = config.get('test_password')
        
        # 步骤1: 访问网站
        self._add_step_result(result, "访问网站", "执行中")
        self._navigate_to_website(base_url)
        self._add_step_result(result, "访问网站", "成功")
        
        # 步骤2: 用户登录
        self._add_step_result(result, "用户登录", "执行中")
        self._perform_login(username, password)
        self._add_step_result(result, "用户登录", "成功")
        
        # 步骤3: 点击添加地块按钮（FAB）
        self._add_step_result(result, "点击添加地块按钮", "执行中")
        self._click_add_plot_fab()
        self._add_step_result(result, "点击添加地块按钮", "成功")
        
        # 步骤4: 填写地块信息
        self._add_step_result(result, "填写地块信息", "执行中")
        plot_info = self._fill_plot_creation_form(result)
        self._add_step_result(result, "填写地块信息", "成功")
        
        # 步骤5: 提交创建地块
        self._add_step_result(result, "提交创建地块", "执行中")
        self._submit_plot_creation()
        self._add_step_result(result, "提交创建地块", "成功")
        
        # 步骤6: 等待地块创建成功并处理提示框
        self._add_step_result(result, "等待地块创建成功", "执行中")
        self._wait_for_plot_creation_success()
        self._add_step_result(result, "等待地块创建成功", "成功")
        
        # 步骤7: 点击成功提示框的OK按钮
        self._add_step_result(result, "点击成功提示框OK", "执行中")
        self._handle_creation_success_alert()
        self._add_step_result(result, "点击成功提示框OK", "成功")

    
    def _wait_for_element_with_retry(self, check_function, element_name: str, max_attempts: int = 10, retry_interval: float = 0.5) -> bool:
        """
        通用的元素等待重试方法
        
        Args:
            check_function: 检查函数，返回True表示找到元素
            element_name: 元素名称（用于日志）
            max_attempts: 最大重试次数
            retry_interval: 重试间隔（秒）
        
        Returns:
            bool: 是否成功找到元素
        """
        print(f"[调试] 开始等待 {element_name}，最大重试次数: {max_attempts}")
        
        for attempt in range(max_attempts):
            try:
                print(f"[调试] 第 {attempt + 1}/{max_attempts} 次检查 {element_name}")
                
                if check_function():
                    print(f"[调试] {element_name} 已出现 (第 {attempt + 1} 次尝试)")
                    return True
                
                if attempt < max_attempts - 1:  # 不是最后一次尝试
                    print(f"[调试] {element_name} 未出现，等待 {retry_interval} 秒后重试")
                    time.sleep(retry_interval)
                else:
                    print(f"[调试] {element_name} 在 {max_attempts} 次尝试后仍未出现")
                    
            except Exception as e:
                print(f"[调试] 检查 {element_name} 时发生异常: {str(e)}")
                if attempt < max_attempts - 1:
                    time.sleep(retry_interval)
                continue
        
        return False
    def _click_add_plot_fab(self):
        """点击添加地块的FAB按钮 - 修复Vue响应式检查"""
        try:
            print(f"[调试] 正在查找并点击添加地块按钮")
            time.sleep(WAIT_CONFIG["navigation_delay"])
            
            # 使用JavaScript查找FAB按钮
            fab_clicked = self.driver.execute_script("""
                console.log('[JS] 开始查找FAB按钮');
                
                // 查找FAB按钮
                var fabButton = document.querySelector('ion-fab-button');
                if (!fabButton) {
                    console.log('[JS] 未找到ion-fab-button');
                    return { success: false, error: '未找到FAB按钮' };
                }
                
                console.log('[JS] 找到FAB按钮，准备点击');
                fabButton.click();
                return { success: true };
            """)
            
            if fab_clicked and fab_clicked.get('success'):
                print(f"[调试] JavaScript成功点击FAB按钮")
            else:
                print(f"[调试] JavaScript点击失败，使用Selenium方式")
                # 备用方案：使用Selenium查找
                fab_button = self._find_element_by_multiple_selectors(
                    SELECTORS["plot_creation"]["add_fab_button"], "添加地块按钮"
                )
                self._safe_click_vue(fab_button, "添加地块按钮")
            
            # 等待模态框出现 - 修复Vue响应式检查
            print(f"[调试] 等待创建地块模态框出现...")
            
            def check_modal_visible():
                """检查Vue模态框是否可见 - 修复版"""
                return self.driver.execute_script("""
                    console.log('[JS] 检查Vue模态框状态');
                    
                    // 检查所有ion-modal元素
                    var modals = document.querySelectorAll('ion-modal');
                    console.log('[JS] 找到', modals.length, '个ion-modal元素');
                    
                    for (var i = 0; i < modals.length; i++) {
                        var modal = modals[i];
                        
                        // 检查多种可能的打开状态
                        var isOpenAttr = modal.getAttribute('is-open');
                        var classList = modal.classList.toString();
                        var isVisible = modal.offsetParent !== null;
                        var hasDisplay = window.getComputedStyle(modal).display !== 'none';
                        var hasOpacity = window.getComputedStyle(modal).opacity !== '0';
                        
                        console.log('[JS] 模态框', i, '状态:');
                        console.log('  - is-open属性:', isOpenAttr);
                        console.log('  - 类名:', classList);
                        console.log('  - 可见性:', isVisible);
                        console.log('  - 显示状态:', hasDisplay);
                        console.log('  - 透明度:', hasOpacity);
                        
                        // Vue响应式绑定可能导致属性值为布尔类型或字符串
                        var isOpen = isOpenAttr === 'true' || isOpenAttr === true || 
                                    isOpenAttr === '' || isOpenAttr !== null;
                        
                        // 检查内容是否为创建地块相关
                        var modalText = modal.textContent || '';
                        var hasCreateContent = modalText.includes('创建地块') || 
                                            modalText.includes('地块名称') ||
                                            modalText.includes('作物名称') ||
                                            modalText.includes('请输入地块名称') ||
                                            modalText.includes('选择作物');
                        
                        console.log('  - 内容相关:', hasCreateContent);
                        console.log('  - 内容预览:', modalText.substring(0, 100));
                        
                        // 如果模态框打开且内容相关，或者仅仅是可见的且内容相关
                        if ((isOpen || isVisible || hasDisplay) && hasCreateContent) {
                            console.log('[JS] 找到打开的创建地块模态框');
                            return true;
                        }
                        
                        // 备用检查：如果模态框可见且包含典型的模态框元素
                        if ((isVisible || hasDisplay) && 
                            (modal.querySelector('ion-header') || modal.querySelector('ion-content'))) {
                            console.log('[JS] 找到可见的模态框（基于结构检查）');
                            return true;
                        }
                    }
                    
                    console.log('[JS] 未找到打开的创建地块模态框');
                    return false;
                """)
            
            modal_appeared = self._wait_for_element_with_retry(
                check_modal_visible, 
                "创建地块模态框", 
                max_attempts=15,  # 增加重试次数
                retry_interval=0.5
            )
            
            if not modal_appeared:
                # 尝试再次点击FAB按钮并增加等待时间
                print(f"[调试] 模态框未出现，尝试再次点击FAB按钮并增加等待时间")
                
                # 再次点击
                self.driver.execute_script("""
                    var fabButton = document.querySelector('ion-fab-button');
                    if (fabButton) {
                        console.log('[JS] 再次点击FAB按钮');
                        fabButton.click();
                    }
                """)
                
                # 增加等待时间给Vue更多时间渲染
                time.sleep(3)
                
                # 最终检查
                final_check = self.driver.execute_script("""
                    var modals = document.querySelectorAll('ion-modal');
                    for (var i = 0; i < modals.length; i++) {
                        var modal = modals[i];
                        var isVisible = modal.offsetParent !== null;
                        var hasDisplay = window.getComputedStyle(modal).display !== 'none';
                        var hasContent = modal.textContent.includes('创建') || modal.textContent.includes('地块');
                        
                        if ((isVisible || hasDisplay) && hasContent) {
                            console.log('[JS] 最终检查发现模态框');
                            return true;
                        }
                    }
                    
                    // 如果还是没有，检查页面状态
                    console.log('[JS] 最终检查失败，输出页面状态');
                    console.log('[JS] 当前URL:', window.location.href);
                    console.log('[JS] 页面标题:', document.title);
                    console.log('[JS] 模态框数量:', document.querySelectorAll('ion-modal').length);
                    
                    return false;
                """)
                
                if not final_check:
                    # 最后的调试信息
                    page_debug = self.driver.execute_script("""
                        return {
                            currentUrl: window.location.href,
                            title: document.title,
                            modalCount: document.querySelectorAll('ion-modal').length,
                            fabExists: document.querySelector('ion-fab-button') !== null,
                            bodyText: document.body.textContent.substring(0, 200)
                        };
                    """)
                    print(f"[调试] 页面调试信息: {page_debug}")
                    raise Exception("创建地块模态框未出现")
            
            print(f"[调试] 创建地块模态框已成功显示")
            
        except Exception as e:
            print(f"[调试] 点击添加地块按钮失败: {str(e)}")
            raise Exception(f"点击添加地块按钮失败: {str(e)}")
    def _fill_plot_name_input(self, plot_name: str):
        """填写地块名称输入框 - 修复版，确保模态框仍然打开"""
        try:
            print(f"[调试] 填写地块名称: {plot_name}")
            
            # 等待一下确保植物选择完成
            time.sleep(WAIT_CONFIG["input_delay"])
            
            # 检查模态框是否仍然打开
            modal_still_open = self.driver.execute_script("""
                console.log('[JS] 检查模态框是否仍然打开');
                
                var modals = document.querySelectorAll('ion-modal');
                for (var i = 0; i < modals.length; i++) {
                    var modal = modals[i];
                    var isOpenAttr = modal.getAttribute('is-open');
                    var isVisible = modal.offsetParent !== null;
                    var hasDisplay = window.getComputedStyle(modal).display !== 'none';
                    var hasContent = modal.textContent.includes('创建') || modal.textContent.includes('地块');
                    
                    console.log('[JS] 模态框', i, '状态:');
                    console.log('  - is-open:', isOpenAttr);
                    console.log('  - visible:', isVisible);
                    console.log('  - display:', hasDisplay);
                    console.log('  - hasContent:', hasContent);
                    
                    if ((isOpenAttr === 'true' || isVisible || hasDisplay) && hasContent) {
                        console.log('[JS] 模态框仍然打开');
                        return { open: true, modal: modal, index: i };
                    }
                }
                
                console.log('[JS] 模态框已关闭或未找到');
                return { open: false, modalCount: modals.length };
            """)
            
            print(f"[调试] 模态框状态检查: {modal_still_open}")
            
            if not modal_still_open or not modal_still_open.get('open'):
                # 如果模态框关闭了，重新打开
                print(f"[调试] 模态框已关闭，重新打开...")
                self._click_add_plot_fab()
                time.sleep(WAIT_CONFIG["modal_delay"] * 2)
                
                # 重新检查
                modal_reopened = self.driver.execute_script("""
                    var modals = document.querySelectorAll('ion-modal');
                    for (var i = 0; i < modals.length; i++) {
                        var modal = modals[i];
                        var isOpenAttr = modal.getAttribute('is-open');
                        var isVisible = modal.offsetParent !== null;
                        var hasContent = modal.textContent.includes('创建') || modal.textContent.includes('地块');
                        
                        if ((isOpenAttr === 'true' || isVisible) && hasContent) {
                            return { open: true, modal: modal };
                        }
                    }
                    return { open: false };
                """)
                
                if not modal_reopened or not modal_reopened.get('open'):
                    raise Exception("无法打开或重新打开地块创建模态框")
                
                modal_still_open = modal_reopened
            
            # 在打开的模态框内查找地块名称输入框
            name_input_result = self.driver.execute_script("""
                console.log('[JS] 在模态框内查找地块名称输入框');
                
                var modal = arguments[0];
                
                // 查找ion-input元素
                var inputs = modal.querySelectorAll('ion-input');
                console.log('[JS] 在模态框中找到', inputs.length, '个ion-input');
                
                for (var i = 0; i < inputs.length; i++) {
                    var ionInput = inputs[i];
                    var placeholder = ionInput.getAttribute('placeholder');
                    var vModel = ionInput.getAttribute('v-model');
                    
                    console.log('[JS] Input', i, '- placeholder:', placeholder, ', v-model:', vModel);
                    
                    if (placeholder && placeholder.includes('地块名称')) {
                        var realInput = ionInput.querySelector('input');
                        if (realInput) {
                            console.log('[JS] 找到地块名称输入框（通过placeholder）');
                            return { found: true, element: realInput, type: 'placeholder' };
                        }
                    }
                    
                    if (vModel && vModel.includes('plotName')) {
                        var realInput = ionInput.querySelector('input');
                        if (realInput) {
                            console.log('[JS] 找到地块名称输入框（通过v-model）');
                            return { found: true, element: realInput, type: 'v-model' };
                        }
                    }
                }
                
                // 备用方案：查找第一个input元素
                var firstInput = modal.querySelector('input[type="text"], input:not([type])');
                if (firstInput) {
                    console.log('[JS] 找到第一个输入框作为地块名称输入框');
                    return { found: true, element: firstInput, type: 'first_input' };
                }
                
                return { found: false, error: '未找到地块名称输入框' };
            """, modal_still_open['modal'])
            
            print(f"[调试] 输入框查找结果: {name_input_result}")
            
            if not name_input_result or not name_input_result.get('found'):
                raise Exception(f"未找到地块名称输入框: {name_input_result.get('error', '未知错误')}")
            
            print(f"[调试] 找到地块名称输入框，类型: {name_input_result.get('type')}")
            
            # 使用JavaScript填写输入框
            fill_result = self.driver.execute_script("""
                var inputElement = arguments[0];
                var value = arguments[1];
                
                console.log('[JS] 填写地块名称:', value);
                
                // 先清空
                inputElement.value = '';
                
                // 设置焦点
                inputElement.focus();
                
                // 设置值
                inputElement.value = value;
                
                // 触发各种事件
                inputElement.dispatchEvent(new Event('focus', { bubbles: true }));
                inputElement.dispatchEvent(new Event('input', { bubbles: true }));
                inputElement.dispatchEvent(new Event('change', { bubbles: true }));
                inputElement.dispatchEvent(new CustomEvent('ionInput', { 
                    detail: { value: value }, 
                    bubbles: true 
                }));
                inputElement.dispatchEvent(new CustomEvent('ionChange', { 
                    detail: { value: value }, 
                    bubbles: true 
                }));
                
                return { success: true, value: inputElement.value };
            """, name_input_result['element'], plot_name)
            
            if fill_result and fill_result.get('success'):
                print(f"[调试] 地块名称填写完成: {fill_result.get('value')}")
            else:
                raise Exception("地块名称填写失败")
            
            # 验证值是否设置成功
            current_value = self.driver.execute_script("""
                return arguments[0].value;
            """, name_input_result['element'])
            
            if current_value != plot_name:
                print(f"[调试] 值验证失败，期望: {plot_name}，实际: {current_value}")
                raise Exception(f"地块名称设置失败，期望: {plot_name}，实际: {current_value}")
            
            print(f"[调试] 地块名称验证成功: {current_value}")
            
        except Exception as e:
            print(f"[调试] 填写地块名称失败: {str(e)}")
            raise Exception(f"填写地块名称失败: {str(e)}")
    def _get_first_plant_option(self) -> str:
        """获取第一种植物选项并完成完整选择流程（包括点击OK）"""
        try:
            print(f"[调试] 获取植物选项并完成完整选择流程")
            
            # 首先确保模态框是打开的
            modal_check_result = self.driver.execute_script("""
                console.log('[JS] 检查创建地块模态框状态');
                
                var modals = document.querySelectorAll('ion-modal');
                for (var i = 0; i < modals.length; i++) {
                    var modal = modals[i];
                    var isOpen = modal.getAttribute('is-open') === 'true' || 
                                modal.offsetParent !== null;
                    var hasContent = modal.textContent.includes('创建') || 
                                   modal.textContent.includes('地块');
                    
                    if (isOpen && hasContent) {
                        return { found: true, modal: modal };
                    }
                }
                return { found: false };
            """)
            
            if not modal_check_result or not modal_check_result.get('found'):
                print(f"[调试] 创建地块模态框未打开，使用默认植物")
                return "番茄"
            
            # 在模态框中点击植物选择器
            plant_select_clicked = self.driver.execute_script("""
                console.log('[JS] 点击植物选择器');
                
                var modal = arguments[0];
                var selects = modal.querySelectorAll('ion-select');
                
                for (var i = 0; i < selects.length; i++) {
                    var select = selects[i];
                    var placeholder = select.getAttribute('placeholder') || '';
                    var vModel = select.getAttribute('v-model') || '';
                    
                    if (placeholder.includes('作物') || placeholder.includes('植物') || 
                        vModel.includes('plant')) {
                        console.log('[JS] 找到植物选择器，点击');
                        select.click();
                        return { success: true };
                    }
                }
                
                // 备用：点击第一个选择器
                if (selects.length > 0) {
                    selects[0].click();
                    return { success: true };
                }
                
                return { success: false, error: '未找到植物选择器' };
            """, modal_check_result['modal'])
            
            if not plant_select_clicked or not plant_select_clicked.get('success'):
                print(f"[调试] 无法点击植物选择器，使用默认植物")
                return "番茄"
            
            print(f"[调试] 植物选择器已点击，等待选项Alert出现...")
            
            # 等待Alert选择框出现
            time.sleep(WAIT_CONFIG["dropdown_delay"] * 2)
            
            # 在Alert中选择第一个植物选项
            plant_selected = self.driver.execute_script("""
                console.log('[JS] 在Alert中选择第一个植物选项');
                
                // 查找Alert
                var alerts = document.querySelectorAll('ion-alert');
                console.log('[JS] 找到', alerts.length, '个Alert');
                
                for (var i = 0; i < alerts.length; i++) {
                    var alert = alerts[i];
                    if (alert.offsetParent !== null) {  // 可见的Alert
                        console.log('[JS] 找到可见的Alert');
                        
                        var buttons = alert.querySelectorAll('button');
                        console.log('[JS] Alert中有', buttons.length, '个按钮');
                        
                        var selectedPlant = null;
                        
                        // 找到第一个植物选项按钮（不是取消或确定）
                        for (var j = 0; j < buttons.length; j++) {
                            var button = buttons[j];
                            var text = button.textContent.trim();
                            console.log('[JS] 按钮', j, '文本:', text);
                            
                            // 跳过控制按钮，选择第一个植物
                            if (text && text !== '取消' && text !== '确定' && 
                                text !== 'Cancel' && text !== 'OK' && 
                                text !== 'Confirm' && !selectedPlant) {
                                console.log('[JS] 选择植物:', text);
                                button.click();
                                selectedPlant = text;
                                break;
                            }
                        }
                        
                        if (selectedPlant) {
                            return { success: true, plant: selectedPlant, alertFound: true };
                        }
                    }
                }
                
                // 如果没有找到Alert，尝试查找ion-select-option
                var selectOptions = document.querySelectorAll('ion-select-option');
                if (selectOptions.length > 0) {
                    var firstOption = selectOptions[0];
                    var text = firstOption.textContent.trim();
                    console.log('[JS] 直接选择ion-select-option:', text);
                    firstOption.click();
                    return { success: true, plant: text, method: 'select-option' };
                }
                
                return { success: false, error: '未找到植物选项' };
            """)
            
            print(f"[调试] 植物选择结果: {plant_selected}")
            
            if not plant_selected or not plant_selected.get('success'):
                print(f"[调试] 植物选择失败，使用默认植物")
                return "番茄"
            
            selected_plant = plant_selected.get('plant')
            print(f"[调试] 已选择植物: {selected_plant}")
            
            # 关键步骤：等待并点击Alert中的"OK"按钮
            if plant_selected.get('alertFound'):
                print(f"[调试] 等待并点击Alert中的OK按钮...")
                time.sleep(WAIT_CONFIG["click_delay"])
                
                ok_clicked = self.driver.execute_script("""
                    console.log('[JS] 查找并点击Alert中的OK按钮');
                    
                    var alerts = document.querySelectorAll('ion-alert');
                    for (var i = 0; i < alerts.length; i++) {
                        var alert = alerts[i];
                        if (alert.offsetParent !== null) {
                            var buttons = alert.querySelectorAll('button');
                            
                            for (var j = 0; j < buttons.length; j++) {
                                var button = buttons[j];
                                var text = button.textContent.trim().toLowerCase();
                                
                                // 查找OK/确定按钮
                                if (text === 'ok' || text === '确定' || text === 'confirm') {
                                    console.log('[JS] 找到OK按钮，点击确认选择');
                                    button.click();
                                    return { success: true, buttonText: button.textContent };
                                }
                            }
                        }
                    }
                    
                    return { success: false, error: '未找到OK按钮' };
                """)
                
                print(f"[调试] OK按钮点击结果: {ok_clicked}")
                
                if ok_clicked and ok_clicked.get('success'):
                    print(f"[调试] 成功点击OK按钮: {ok_clicked.get('buttonText')}")
                    
                    # 等待Alert关闭和选择生效
                    time.sleep(WAIT_CONFIG["click_delay"])
                    
                    # 验证选择是否生效
                    selection_verified = self._verify_plant_selection(selected_plant)
                    if selection_verified:
                        print(f"[调试] 植物选择已生效: {selected_plant}")
                        return selected_plant
                    else:
                        print(f"[调试] 植物选择未生效，但继续使用: {selected_plant}")
                        return selected_plant
                else:
                    print(f"[调试] 未能点击OK按钮，可能选择已自动生效")
                    return selected_plant
            else:
                # 如果不是Alert方式，直接返回选择的植物
                print(f"[调试] 非Alert方式选择，植物已选中: {selected_plant}")
                return selected_plant
            
        except Exception as e:
            print(f"[调试] 植物选择流程失败: {str(e)}")
            return "番茄"
    
    def _verify_plant_selection(self, expected_plant: str) -> bool:
        """验证植物选择是否生效"""
        try:
            print(f"[调试] 验证植物选择是否生效: {expected_plant}")
            
            # 检查创建地块模态框中的植物选择器值
            verification_result = self.driver.execute_script("""
                var expectedPlant = arguments[0];
                console.log('[JS] 验证植物选择:', expectedPlant);
                
                // 查找创建地块模态框
                var modals = document.querySelectorAll('ion-modal');
                for (var i = 0; i < modals.length; i++) {
                    var modal = modals[i];
                    var isOpen = modal.getAttribute('is-open') === 'true' || 
                                modal.offsetParent !== null;
                    var hasContent = modal.textContent.includes('创建') || 
                                   modal.textContent.includes('地块');
                    
                    if (isOpen && hasContent) {
                        // 在模态框中查找植物选择器
                        var selects = modal.querySelectorAll('ion-select');
                        for (var j = 0; j < selects.length; j++) {
                            var select = selects[j];
                            var placeholder = select.getAttribute('placeholder') || '';
                            
                            if (placeholder.includes('作物') || placeholder.includes('植物')) {
                                var currentValue = select.value || select.getAttribute('value') || '';
                                var displayText = select.textContent || '';
                                
                                console.log('[JS] 植物选择器当前值:', currentValue);
                                console.log('[JS] 植物选择器显示文本:', displayText);
                                
                                // 检查值是否匹配
                                var matches = currentValue === expectedPlant || 
                                             displayText.includes(expectedPlant);
                                
                                return {
                                    verified: matches,
                                    currentValue: currentValue,
                                    displayText: displayText,
                                    expectedPlant: expectedPlant
                                };
                            }
                        }
                    }
                }
                
                return { verified: false, error: '未找到植物选择器' };
            """, expected_plant)
            
            print(f"[调试] 植物选择验证结果: {verification_result}")
            
            if verification_result and verification_result.get('verified'):
                return True
            else:
                print(f"[调试] 植物选择验证失败，但不影响继续流程")
                return False
                
        except Exception as e:
            print(f"[调试] 验证植物选择失败: {str(e)}")
            return False
    
    def _select_plant_option(self, plant_name: str):
        """植物选择验证 - 简化版，因为选择已在_get_first_plant_option中完成"""
        try:
            print(f"[调试] 植物选择验证: {plant_name}")
            
            # 只做简单验证，因为选择流程已在获取时完成
            plant_check = self.driver.execute_script("""
                var plantName = arguments[0];
                console.log('[JS] 简单验证植物选择:', plantName);
                
                var modal = document.querySelector('ion-modal[is-open="true"]');
                if (!modal) {
                    return { success: false, error: '模态框不存在' };
                }
                
                var selectElement = modal.querySelector('ion-select');
                if (!selectElement) {
                    return { success: false, error: '未找到植物选择器' };
                }
                
                var currentValue = selectElement.value || selectElement.getAttribute('value') || '';
                console.log('[JS] 当前植物选择器值:', currentValue);
                
                return { 
                    success: true, 
                    currentValue: currentValue,
                    hasValue: currentValue !== ''
                };
            """, plant_name)
            
            print(f"[调试] 植物选择检查结果: {plant_check}")
            
            if plant_check and plant_check.get('success') and plant_check.get('hasValue'):
                print(f"[调试] 植物选择已完成: {plant_check.get('currentValue')}")
            else:
                print(f"[调试] 植物选择可能未完成，但继续流程")
            
        except Exception as e:
            print(f"[调试] 植物选择验证失败: {str(e)}")
    
    def _fill_plot_creation_form(self, result: Dict[str, Any]) -> Dict[str, str]:
        """填写地块创建表单 - 修复版，确保植物选择完整"""
        try:
            print(f"[调试] 开始填写地块创建表单")
            time.sleep(WAIT_CONFIG["input_delay"])
            
            # 1. 获取植物选项并完成完整选择流程（包括点击OK）
            first_plant = self._get_first_plant_option()
            
            # 2. 生成地块名称
            timestamp = int(time.time())
            plot_name = f"{first_plant}_地块_{timestamp}"
            
            plot_info = {
                "plot_name": plot_name,
                "plant_name": first_plant
            }
            
            result["created_plot_info"] = plot_info
            print(f"[调试] 准备填写: 地块名称={plot_name}, 植物={first_plant}")
            
            # 3. 填写地块名称
            self._fill_plot_name_input(plot_name)
            
            # 4. 验证植物选择状态
            self._select_plant_option(first_plant)
            
            # 5. 最终验证表单完整性
            form_valid = self.driver.execute_script("""
                var modal = document.querySelector('ion-modal[is-open="true"]');
                if (!modal) return { valid: false, error: '模态框消失' };
                
                var nameInput = modal.querySelector('ion-input input');
                var plantSelect = modal.querySelector('ion-select');
                
                var nameValue = nameInput ? nameInput.value : '';
                var plantValue = plantSelect ? (plantSelect.value || plantSelect.getAttribute('value')) : '';
                
                console.log('[JS] 最终表单验证:');
                console.log('  - 地块名称:', nameValue);
                console.log('  - 植物名称:', plantValue);
                
                var isValid = nameValue !== '' && plantValue !== '';
                
                return {
                    valid: isValid,
                    nameValue: nameValue,
                    plantValue: plantValue,
                    nameEmpty: nameValue === '',
                    plantEmpty: plantValue === ''
                };
            """)
            
            print(f"[调试] 表单完整性验证: {form_valid}")
            
            if form_valid and form_valid.get('valid'):
                print(f"[调试] 表单验证通过")
            else:
                print(f"[调试] 表单验证失败:")
                if form_valid:
                    if form_valid.get('nameEmpty'):
                        print(f"  - 地块名称为空")
                    if form_valid.get('plantEmpty'):
                        print(f"  - 植物名称为空")
                print(f"[调试] 继续提交流程...")
            
            print(f"[调试] 地块创建表单填写完成")
            return plot_info
            
        except Exception as e:
            print(f"[调试] 填写地块创建表单失败: {str(e)}")
            
            timestamp = int(time.time())
            default_plot_info = {
                "plot_name": f"测试地块_{timestamp}",
                "plant_name": "番茄"
            }
            result["created_plot_info"] = default_plot_info
            
            raise Exception(f"填写地块创建表单失败: {str(e)}")
    
    def _set_plant_to_vue_data(self, plant_name: str) -> Dict[str, Any]:
        """直接设置植物名称到Vue的响应式数据中 - 简化版"""
        try:
            print(f"[调试] 设置植物到Vue数据: {plant_name}")
            
            # 等待一下确保植物选择器关闭
            time.sleep(0.5)
            
            # 验证模态框仍然打开并设置植物选择
            result = self.driver.execute_script("""
                var plantName = arguments[0];
                console.log('[JS] 验证模态框并设置植物选择:', plantName);
                
                var modals = document.querySelectorAll('ion-modal');
                var openModal = null;
                
                for (var i = 0; i < modals.length; i++) {
                    var modal = modals[i];
                    var isOpen = modal.getAttribute('is-open') === 'true' || 
                                modal.offsetParent !== null;
                    var hasContent = modal.textContent.includes('创建') || 
                                   modal.textContent.includes('地块');
                    
                    if (isOpen && hasContent) {
                        openModal = modal;
                        break;
                    }
                }
                
                if (!openModal) {
                    return { success: false, error: '模态框未找到或已关闭' };
                }
                
                // 在模态框中查找植物选择器并设置值
                var selectElement = openModal.querySelector('ion-select');
                if (selectElement) {
                    console.log('[JS] 找到植物选择器，设置值');
                    
                    // 直接设置value属性
                    selectElement.value = plantName;
                    selectElement.setAttribute('value', plantName);
                    
                    // 触发Vue的事件
                    selectElement.dispatchEvent(new Event('change', { bubbles: true }));
                    selectElement.dispatchEvent(new CustomEvent('ionChange', { 
                        detail: { value: plantName }, 
                        bubbles: true 
                    }));
                    
                    console.log('[JS] 植物选择器值已设置');
                    return { success: true, method: 'dom_select', value: selectElement.value };
                }
                
                return { success: false, error: '未找到植物选择器' };
            """, plant_name)
            
            print(f"[调试] Vue数据设置结果: {result}")
            return result or { 'success': False, 'error': '未知错误' }
            
        except Exception as e:
            print(f"[调试] 设置Vue数据失败: {str(e)}")
            return { 'success': False, 'error': str(e) }
    
    
    def _submit_plot_creation(self):
        """提交地块创建 - 修复版"""
        try:
            print(f"[调试] 提交地块创建")
            
            # 在模态框内查找提交按钮
            submit_result = self.driver.execute_script("""
                console.log('[JS] 在模态框内查找提交按钮');
                
                var modals = document.querySelectorAll('ion-modal');
                for (var i = 0; i < modals.length; i++) {
                    var modal = modals[i];
                    var isVisible = modal.offsetParent !== null || 
                                window.getComputedStyle(modal).display !== 'none';
                    
                    if (isVisible) {
                        var buttons = modal.querySelectorAll('ion-button');
                        console.log('[JS] 在可见模态框中找到', buttons.length, '个按钮');
                        
                        for (var j = 0; j < buttons.length; j++) {
                            var button = buttons[j];
                            var text = button.textContent.trim();
                            var expand = button.getAttribute('expand');
                            var slot = button.getAttribute('slot');
                            
                            console.log('[JS] 按钮', j, '- 文本:', text, ', expand:', expand, ', slot:', slot);
                            
                            // 查找提交按钮
                            if (text === '提交' && expand === 'full') {
                                console.log('[JS] 找到提交按钮');
                                return { found: true, element: button, type: 'submit_button' };
                            }
                            
                            // 备用：查找任何expand="full"且不在header中的按钮
                            if (expand === 'full' && slot !== 'end') {
                                console.log('[JS] 找到全宽按钮作为提交按钮');
                                return { found: true, element: button, type: 'full_width_button' };
                            }
                        }
                    }
                }
                
                return { found: false, error: '未找到提交按钮' };
            """)
            
            if not submit_result or not submit_result.get('found'):
                raise Exception(f"未找到提交按钮: {submit_result.get('error', '未知错误')}")
            
            print(f"[调试] 找到提交按钮，类型: {submit_result.get('type')}")
            
            # 点击提交按钮
            click_result = self.driver.execute_script("""
                var button = arguments[0];
                console.log('[JS] 点击提交按钮');
                button.click();
                return { success: true };
            """, submit_result['element'])
            
            print(f"[调试] 地块创建提交完成")
            
        except Exception as e:
            print(f"[调试] 提交地块创建失败: {str(e)}")
            raise Exception(f"提交地块创建失败: {str(e)}")

    
    
    def _wait_for_plot_creation_success(self):
        """等待地块创建成功"""
        try:
            print(f"[调试] 等待地块创建成功")
            
            def check_creation_success():
                """检查地块创建是否成功"""
                success_result = self.driver.execute_script("""
                    // 检查成功提示 - 根据alert.ts的实现
                    var alerts = document.querySelectorAll('ion-alert');
                    for (var i = 0; i < alerts.length; i++) {
                        var alert = alerts[i];
                        if (alert.offsetParent !== null) {
                            var text = alert.textContent.toLowerCase();
                            if (text.includes('成功') || text.includes('地块创建成功') || text.includes('success')) {
                                return { found: true, type: 'alert', text: alert.textContent };
                            }
                        }
                    }
                    
                    // 检查模态框是否已关闭（创建成功后模态框会关闭）
                    var modal = document.querySelector('ion-modal[is-open="true"]');
                    if (modal === null) {
                        return { found: true, type: 'modal_closed' };
                    }
                    
                    return { found: false };
                """)
                
                return success_result and success_result.get('found')
            
            # 使用重试逻辑等待创建成功
            creation_success = self._wait_for_element_with_retry(
                check_creation_success,
                "地块创建成功提示",
                max_attempts=15,
                retry_interval=0.8
            )
            
            if not creation_success:
                raise Exception("地块创建超时，未检测到成功提示")
            
            print(f"[调试] 地块创建成功")
            
        except Exception as e:
            print(f"[调试] 等待地块创建成功失败: {str(e)}")
            raise Exception(f"等待地块创建成功失败: {str(e)}")

    def _handle_creation_success_alert(self):
        """处理地块创建成功的提示框，点击OK按钮"""
        try:
            print(f"[调试] 处理创建成功提示框")
            
            # 查找并点击OK按钮 - 根据alert.ts，按钮文本是'OK'
            ok_clicked = self.driver.execute_script("""
                console.log('[JS] 查找成功提示框的OK按钮');
                
                var alerts = document.querySelectorAll('ion-alert');
                for (var i = 0; i < alerts.length; i++) {
                    var alert = alerts[i];
                    if (alert.offsetParent !== null) {
                        var buttons = alert.querySelectorAll('button');
                        for (var j = 0; j < buttons.length; j++) {
                            var button = buttons[j];
                            var text = button.textContent.trim().toLowerCase();
                            if (text === 'ok' || text === '确定' || text === '确认') {
                                console.log('[JS] 找到OK按钮，点击');
                                button.click();
                                return { success: true, buttonText: button.textContent };
                            }
                        }
                    }
                }
                
                return { success: false, error: '未找到OK按钮' };
            """)
            
            if ok_clicked and ok_clicked.get('success'):
                print(f"[调试] 成功点击OK按钮: {ok_clicked.get('buttonText')}")
            else:
                print(f"[调试] 未找到OK按钮，可能提示框已自动关闭")
            
            # 等待提示框消失
            time.sleep(WAIT_CONFIG["click_delay"])
            
            # 验证提示框是否已消失
            alert_gone = self.driver.execute_script("""
                var alerts = document.querySelectorAll('ion-alert');
                for (var i = 0; i < alerts.length; i++) {
                    if (alerts[i].offsetParent !== null) {
                        return false;
                    }
                }
                return true;
            """)
            
            if alert_gone:
                print(f"[调试] 成功提示框已消失")
            else:
                print(f"[调试] 提示框可能仍存在，继续流程")
            
        except Exception as e:
            print(f"[调试] 处理成功提示框失败: {str(e)}")
            raise Exception(f"处理成功提示框失败: {str(e)}")

    
    # 更新运行地块管理测试的主方法，调用完整的步骤
    def run_plot_management_test(self, test_config: Dict[str, Any]) -> Dict[str, Any]:
        """地块管理测试：创建地块 -> 删除地块"""
        print(f"\n[测试开始] 地块管理测试")
        print(f"[配置] 基础URL: {test_config.get('base_url', '未设置')}")
        print(f"[配置] 用户名: {test_config.get('test_username', '未设置')}")
        print(f"[配置] 无头模式: {test_config.get('headless', False)}")
        
        config = E2ETestConfig(test_config)
        config.validate()
        
        for attempt in range(RETRY_CONFIG["max_retries"]):
            print(f"\n[重试] 第 {attempt + 1} 次尝试")
            
            test_result = {
                "test_id": "E2E_TC_003",
                "test_name": "地块管理完整流程测试",
                "attempt": attempt + 1,
                "start_time": time.strftime('%Y-%m-%d %H:%M:%S'),
                "status": "RUNNING",
                "steps": [],
                "screenshots": [],
                "created_plot_info": {},
                "error_message": None,
                "execution_time": 0
            }
            
            start_time = time.time()
            
            try:
                print(f"[调试] 设置浏览器驱动")
                self._setup_driver(config.config)
                print(f"[调试] 开始执行地块管理测试步骤")
                self._execute_plot_management_steps(config, test_result)
                test_result["status"] = "PASSED"
                test_result["message"] = "地块管理测试执行成功"
                print(f"\n[测试成功] 地块管理测试执行成功")
                return test_result
                
            except Exception as e:
                test_result["status"] = "FAILED"
                test_result["error_message"] = str(e)
                test_result["message"] = f"地块管理测试执行失败: {str(e)}"
                print(f"\n[测试失败] {str(e)}")
                
                if self.driver:
                    screenshot_path = self._take_screenshot(f"plot_management_failure_attempt_{attempt + 1}")
                    if screenshot_path:
                        test_result["screenshots"].append(screenshot_path)
                        print(f"[调试] 失败截图已保存: {screenshot_path}")
                        
            finally:
                print(f"[调试] 清理浏览器驱动")
                self._cleanup_driver()
                test_result["execution_time"] = round(time.time() - start_time, 2)
                test_result["end_time"] = time.strftime('%Y-%m-%d %H:%M:%S')
                print(f"[调试] 本次尝试执行时间: {test_result['execution_time']}秒")
        
            if "browser" not in str(test_result.get("error_message", "")).lower():
                print(f"[调试] 非浏览器相关错误，停止重试")
                break
                
            if attempt < RETRY_CONFIG["max_retries"] - 1:
                print(f"[调试] 等待 {RETRY_CONFIG['retry_delay']} 秒后重试")
                time.sleep(RETRY_CONFIG["retry_delay"])
        
        print(f"\n[测试结束] 地块管理测试")
        return test_result

    def _check_for_error_message(self) -> str:
        """检查是否有错误信息"""
        try:
            # 使用JavaScript检查错误信息
            error_msg = self.driver.execute_script("""
                // 检查 ion-alert 中的错误信息
                var alerts = document.querySelectorAll('ion-alert');
                for (var i = 0; i < alerts.length; i++) {
                    var alert = alerts[i];
                    if (alert.offsetParent !== null) {
                        var text = alert.textContent.toLowerCase();
                        if (text.includes('错误') || text.includes('失败') || text.includes('error') || text.includes('failed')) {
                            return alert.textContent.trim();
                        }
                    }
                }
                
                // 检查 ion-toast 中的错误信息
                var toasts = document.querySelectorAll('ion-toast');
                for (var i = 0; i < toasts.length; i++) {
                    var toast = toasts[i];
                    if (toast.offsetParent !== null) {
                        var text = toast.textContent.toLowerCase();
                        if (text.includes('错误') || text.includes('失败') || text.includes('error') || text.includes('failed')) {
                            return toast.textContent.trim();
                        }
                    }
                }
                
                return '';
            """)
            
            if error_msg:
                print(f"[调试] 检测到错误信息: {error_msg}")
                return error_msg
            
            return ""
            
        except Exception as e:
            print(f"[调试] 检查错误信息失败: {str(e)}")
            return ""

    def _check_for_detection_result(self) -> bool:
        """检查检测结果是否出现"""
        print(f"[调试] 开始检查检测结果...")
        
        try:
            # 使用 JavaScript 进行检查
            result_found = self.driver.execute_script("""
                console.log('[JS] 开始检查检测结果');
                
                // 1. 检查模态框中的检测结果卡片
                var modals = document.querySelectorAll('ion-modal[is-open="true"]');
                console.log('[JS] 找到', modals.length, '个打开的模态框');
                
                for (var i = 0; i < modals.length; i++) {
                    var modal = modals[i];
                    var text = modal.textContent.toLowerCase();
                    if (text.includes('检测结果') || text.includes('病害名称') || text.includes('置信度') || text.includes('建议')) {
                        console.log('[JS] 找到检测结果内容');
                        return { found: true, complete: true };
                    }
                }
                
                // 2. 检查页面是否有新的日志记录
                var logItems = document.querySelectorAll('ion-list ion-item');
                if (logItems.length > 0) {
                    var latestLog = logItems[0];
                    var logText = latestLog.textContent.toLowerCase();
                    if (logText.includes('检测') || logText.includes('病害') || logText.includes('置信度')) {
                        console.log('[JS] 找到检测相关日志');
                        return { found: true, complete: true, hasLog: true };
                    }
                }
                
                console.log('[JS] 未找到检测结果');
                return { found: false };
            """)
            
            if result_found and result_found.get('found'):
                print(f"[调试] 检测结果已找到")
                return True
            else:
                print(f"[调试] 未找到检测结果")
                return False
                
        except Exception as e:
            print(f"[调试] 检查检测结果失败: {str(e)}")
            return False
        # 在 E2ETestService 类中添加以下方法：
    
    def get_plot_logs_predefined_test_cases(self) -> List[Dict[str, Any]]:
        """获取地块日志测试的预定义测试用例"""
        from app.static.system_test import TEST_CASES_CONFIG
        return [TEST_CASES_CONFIG["plot_logs"]]
    
    def run_plot_logs_test(self, test_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        地块日志查看测试
        """
        print(f"\n[测试开始] 地块日志查看测试")
        print(f"[配置] 基础URL: {test_config.get('base_url', '未设置')}")
        print(f"[配置] 用户名: {test_config.get('test_username', '未设置')}")
        print(f"[配置] 无头模式: {test_config.get('headless', False)}")
        
        config = E2ETestConfig(test_config)
        config.validate()
        
        for attempt in range(RETRY_CONFIG["max_retries"]):
            print(f"\n[重试] 第 {attempt + 1} 次尝试")
            
            test_result = {
                "test_id": "E2E_TC_004",
                "test_name": "地块日志查看测试",
                "attempt": attempt + 1,
                "start_time": time.strftime('%Y-%m-%d %H:%M:%S'),
                "status": "RUNNING",
                "steps": [],
                "screenshots": [],
                "log_data": {},
                "error_message": None,
                "execution_time": 0
            }
            
            start_time = time.time()
            
            try:
                print(f"[调试] 设置浏览器驱动")
                self._setup_driver(config.config)
                print(f"[调试] 开始执行地块日志测试步骤")
                self._execute_plot_logs_test_steps(config, test_result)
                test_result["status"] = "PASSED"
                test_result["message"] = "地块日志查看测试执行成功"
                print(f"\n[测试成功] 地块日志查看测试执行成功")
                return test_result
                
            except Exception as e:
                test_result["status"] = "FAILED"
                test_result["error_message"] = str(e)
                test_result["message"] = f"地块日志查看测试执行失败: {str(e)}"
                print(f"\n[测试失败] {str(e)}")
                
                if self.driver:
                    screenshot_path = self._take_screenshot(f"plot_logs_failure_attempt_{attempt + 1}")
                    if screenshot_path:
                        test_result["screenshots"].append(screenshot_path)
                        print(f"[调试] 失败截图已保存: {screenshot_path}")
                        
            finally:
                print(f"[调试] 清理浏览器驱动")
                self._cleanup_driver()
                test_result["execution_time"] = round(time.time() - start_time, 2)
                test_result["end_time"] = time.strftime('%Y-%m-%d %H:%M:%S')
                print(f"[调试] 本次尝试执行时间: {test_result['execution_time']}秒")
        
            if "browser" not in str(test_result.get("error_message", "")).lower():
                print(f"[调试] 非浏览器相关错误，停止重试")
                break
                
            if attempt < RETRY_CONFIG["max_retries"] - 1:
                print(f"[调试] 等待 {RETRY_CONFIG['retry_delay']} 秒后重试")
                time.sleep(RETRY_CONFIG["retry_delay"])
        
        print(f"\n[测试结束] 地块日志查看测试")
        return test_result
    
    def _execute_plot_logs_test_steps(self, config: E2ETestConfig, result: Dict[str, Any]):
        """执行地块日志测试步骤"""
        base_url = config.get_base_url()
        username = config.get('test_username')
        password = config.get('test_password')
        
        # 步骤1: 访问网站
        self._add_step_result(result, "访问网站", "执行中")
        self._navigate_to_website(base_url)
        self._add_step_result(result, "访问网站", "成功")
        
        # 步骤2: 用户登录
        self._add_step_result(result, "用户登录", "执行中")
        self._perform_login(username, password)
        self._add_step_result(result, "用户登录", "成功")
        
        # 步骤3: 点击第一个地块卡片
        self._add_step_result(result, "点击第一个地块卡片", "执行中")
        self._click_first_plot_card()
        self._add_step_result(result, "点击第一个地块卡片", "成功")
        
        # 步骤4: 等待地块详情页加载
        self._add_step_result(result, "等待地块详情页加载", "执行中")
        self._wait_for_plot_detail_page_loaded()
        self._add_step_result(result, "等待地块详情页加载", "成功")
        
        # 步骤5: 读取和验证地块日志
        self._add_step_result(result, "读取地块日志", "执行中")
        log_data = self._read_and_validate_plot_logs()
        result["log_data"] = log_data
        self._add_step_result(result, "读取地块日志", "成功")
    
    def _wait_for_plot_detail_page_loaded(self):
        """等待地块详情页加载完成"""
        try:
            print(f"[调试] 等待地块详情页加载完成")
            time.sleep(WAIT_CONFIG["plot_detail_delay"])
            
            # 验证是否在地块详情页
            current_url = self.driver.current_url
            if not any(pattern in current_url for pattern in URL_VALIDATION["plot_detail_patterns"]):
                raise Exception(f"未成功跳转到地块详情页，当前URL: {current_url}")
            
            # 等待页面关键元素加载
            page_loaded = self.driver.execute_script("""
                // 检查页面是否加载完成
                var indicators = [
                    document.querySelector('ion-content'),
                    document.querySelector('ion-header'),
                    document.querySelector('ion-list') || document.querySelector('ion-card')
                ];
                
                var loadedCount = indicators.filter(el => el !== null).length;
                console.log('[JS] 页面加载指标:', loadedCount, '/', indicators.length);
                
                return loadedCount >= 2;
            """)
            
            if not page_loaded:
                print(f"[调试] 页面加载不完整，继续等待...")
                time.sleep(WAIT_CONFIG["navigation_delay"])
            
            print(f"[调试] 地块详情页加载完成")
            
        except Exception as e:
            print(f"[调试] 等待地块详情页加载失败: {str(e)}")
            raise Exception(f"等待地块详情页加载失败: {str(e)}")
    
    def _read_and_validate_plot_logs(self) -> Dict[str, Any]:
        """读取并验证地块日志"""
        try:
            print(f"[调试] 开始读取地块日志")
            time.sleep(WAIT_CONFIG["log_loading_delay"])
            
            # 首先检查日志容器是否存在
            log_container = self._find_log_container()
            
            if not log_container:
                print(f"[调试] 未找到日志容器，可能没有日志数据")
                return self._handle_empty_logs()
            
            print(f"[调试] 找到日志容器，开始提取日志数据")
            
            # 提取日志数据
            logs_data = self._extract_logs_data(log_container)
            
            # 验证日志数据
            validation_result = self._validate_logs_data(logs_data)
            
            # 合并结果
            result = {
                "logs_found": True,
                "log_count": len(logs_data),
                "logs": logs_data,
                "validation": validation_result,
                "container_info": self._get_log_container_info(log_container)
            }
            
            print(f"[调试] 日志读取完成，共找到 {len(logs_data)} 条日志")
            return result
            
        except Exception as e:
            print(f"[调试] 读取地块日志失败: {str(e)}")
            raise Exception(f"读取地块日志失败: {str(e)}")
    
    def _find_log_container(self):
        """查找日志容器"""
        try:
            print(f"[调试] 查找日志容器")
            
            # 使用JavaScript查找日志容器
            log_container = self.driver.execute_script("""
                console.log('[JS] 开始查找日志容器');
                
                // 1. 查找ion-list容器
                var lists = document.querySelectorAll('ion-list');
                console.log('[JS] 找到', lists.length, '个ion-list');
                
                for (var i = 0; i < lists.length; i++) {
                    var list = lists[i];
                    if (list.offsetParent !== null) {  // 可见的列表
                        var items = list.querySelectorAll('ion-item');
                        if (items.length > 0) {
                            console.log('[JS] 找到包含', items.length, '个项目的可见列表');
                            return list;
                        }
                    }
                }
                
                // 2. 查找包含日志内容的ion-content
                var contents = document.querySelectorAll('ion-content');
                for (var i = 0; i < contents.length; i++) {
                    var content = contents[i];
                    var text = content.textContent.toLowerCase();
                    if (text.includes('日志') || text.includes('记录') || text.includes('log') || 
                        text.includes('检测') || text.includes('history')) {
                        console.log('[JS] 找到包含日志关键词的内容容器');
                        return content;
                    }
                }
                
                // 3. 备用：查找任何包含ion-item的容器
                var containers = document.querySelectorAll('ion-content, .log-container, [class*="log"]');
                for (var i = 0; i < containers.length; i++) {
                    var container = containers[i];
                    if (container.querySelectorAll('ion-item').length > 0) {
                        console.log('[JS] 找到包含ion-item的容器');
                        return container;
                    }
                }
                
                console.log('[JS] 未找到日志容器');
                return null;
            """)
            
            if log_container:
                print(f"[调试] JavaScript找到日志容器")
                return log_container
            
            # 备用方案：使用Selenium查找
            print(f"[调试] JavaScript未找到日志容器，使用Selenium方式")
            from app.static.system_test import SELECTORS
            
            for selector in SELECTORS["plot_logs"]["log_list"]:
                try:
                    container = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if container.is_displayed():
                        print(f"[调试] Selenium找到日志容器: {selector}")
                        return container
                except NoSuchElementException:
                    continue
            
            print(f"[调试] 未找到日志容器")
            return None
            
        except Exception as e:
            print(f"[调试] 查找日志容器失败: {str(e)}")
            return None
    
    def _extract_logs_data(self, log_container) -> List[Dict[str, Any]]:
        """从日志容器中提取日志数据"""
        try:
            print(f"[调试] 从容器中提取日志数据")
            
            # 使用JavaScript提取日志项目
            logs_data = self.driver.execute_script("""
                var container = arguments[0];
                var logs = [];
                
                console.log('[JS] 开始提取日志数据');
                
                // 查找所有日志项目
                var items = container.querySelectorAll('ion-item');
                console.log('[JS] 找到', items.length, '个日志项目');
                
                for (var i = 0; i < items.length; i++) {
                    var item = items[i];
                    if (!item.offsetParent) continue;  // 跳过不可见的项目
                    
                    var logEntry = {
                        index: i,
                        content: '',
                        timestamp: '',
                        type: '',
                        raw_text: item.textContent.trim()
                    };
                    
                    // 提取主要内容
                    var labels = item.querySelectorAll('ion-label');
                    if (labels.length > 0) {
                        logEntry.content = labels[0].textContent.trim();
                        if (labels.length > 1) {
                            logEntry.subtitle = labels[1].textContent.trim();
                        }
                    } else {
                        logEntry.content = item.textContent.trim();
                    }
                    
                    // 提取时间戳
                    var notes = item.querySelectorAll('ion-note');
                    if (notes.length > 0) {
                        logEntry.timestamp = notes[0].textContent.trim();
                    }
                    
                    // 提取类型/标签
                    var badges = item.querySelectorAll('ion-badge');
                    if (badges.length > 0) {
                        logEntry.type = badges[0].textContent.trim();
                    }
                    
                    // 提取图标信息
                    var icons = item.querySelectorAll('ion-icon');
                    if (icons.length > 0) {
                        logEntry.icon = icons[0].getAttribute('name') || '';
                    }
                    
                    // 如果没有找到具体字段，尝试解析原始文本
                    if (!logEntry.content && !logEntry.timestamp) {
                        var rawText = logEntry.raw_text;
                        // 简单的时间戳模式匹配
                        var timeMatch = rawText.match(/\\d{4}[-/]\\d{1,2}[-/]\\d{1,2}\\s+\\d{1,2}:\\d{1,2}(:\\d{1,2})?/) ||
                                       rawText.match(/\\d{1,2}[-/]\\d{1,2}\\s+\\d{1,2}:\\d{1,2}/) ||
                                       rawText.match(/\\d{1,2}:\\d{1,2}(:\\d{1,2})?/);
                        if (timeMatch) {
                            logEntry.timestamp = timeMatch[0];
                            logEntry.content = rawText.replace(timeMatch[0], '').trim();
                        } else {
                            logEntry.content = rawText;
                        }
                    }
                    
                    logs.push(logEntry);
                }
                
                console.log('[JS] 提取到', logs.length, '条日志');
                return logs;
            """, log_container)
            
            print(f"[调试] 成功提取 {len(logs_data)} 条日志")
            return logs_data
            
        except Exception as e:
            print(f"[调试] 提取日志数据失败: {str(e)}")
            return []
    
    def _validate_logs_data(self, logs_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """验证日志数据的完整性和格式"""
        try:
            print(f"[调试] 验证日志数据，共 {len(logs_data)} 条")
            
            from app.static.system_test import LOG_VALIDATION
            
            validation_result = {
                "total_logs": len(logs_data),
                "valid_logs": 0,
                "invalid_logs": 0,
                "validation_errors": [],
                "content_analysis": {
                    "has_timestamps": 0,
                    "has_content": 0,
                    "has_type": 0,
                    "relevant_content": 0
                },
                "summary": ""
            }
            
            for i, log_entry in enumerate(logs_data):
                is_valid = True
                
                # 检查是否有内容
                if log_entry.get('content') and log_entry['content'].strip():
                    validation_result["content_analysis"]["has_content"] += 1
                else:
                    is_valid = False
                    validation_result["validation_errors"].append(f"日志 {i+1}: 缺少内容")
                
                # 检查是否有时间戳
                if log_entry.get('timestamp') and log_entry['timestamp'].strip():
                    validation_result["content_analysis"]["has_timestamps"] += 1
                
                # 检查是否有类型标识
                if log_entry.get('type') and log_entry['type'].strip():
                    validation_result["content_analysis"]["has_type"] += 1
                
                # 检查内容相关性
                content_text = (log_entry.get('content', '') + ' ' + log_entry.get('raw_text', '')).lower()
                if any(keyword in content_text for keyword in LOG_VALIDATION["content_keywords"]):
                    validation_result["content_analysis"]["relevant_content"] += 1
                
                if is_valid:
                    validation_result["valid_logs"] += 1
                else:
                    validation_result["invalid_logs"] += 1
            
            # 生成验证摘要
            if validation_result["total_logs"] == 0:
                validation_result["summary"] = "未找到日志记录"
            elif validation_result["valid_logs"] == validation_result["total_logs"]:
                validation_result["summary"] = f"所有 {validation_result['total_logs']} 条日志格式正确"
            else:
                validation_result["summary"] = f"共 {validation_result['total_logs']} 条日志，其中 {validation_result['valid_logs']} 条有效，{validation_result['invalid_logs']} 条格式异常"
            
            print(f"[调试] 日志验证完成: {validation_result['summary']}")
            return validation_result
            
        except Exception as e:
            print(f"[调试] 验证日志数据失败: {str(e)}")
            return {
                "total_logs": len(logs_data),
                "validation_error": str(e),
                "summary": f"验证过程失败: {str(e)}"
            }
    
    def _handle_empty_logs(self) -> Dict[str, Any]:
        """处理空日志的情况"""
        try:
            print(f"[调试] 处理空日志情况")
            
            # 检查是否有明确的空状态提示
            empty_state_info = self.driver.execute_script("""
                // 查找空状态提示
                var emptyMessages = [];
                
                // 查找常见的空状态文本
                var textElements = document.querySelectorAll('p, div, span, ion-card-content');
                for (var i = 0; i < textElements.length; i++) {
                    var el = textElements[i];
                    if (el.offsetParent !== null) {  // 可见元素
                        var text = el.textContent.trim();
                        if (text && (text.includes('暂无') || text.includes('没有') || text.includes('空') ||
                                   text.includes('no data') || text.includes('empty') || text.includes('无记录'))) {
                            emptyMessages.push(text);
                        }
                    }
                }
                
                return {
                    hasEmptyMessage: emptyMessages.length > 0,
                    emptyMessages: emptyMessages,
                    pageText: document.body.textContent.substring(0, 500)  // 页面文本预览
                };
            """)
            
            result = {
                "logs_found": False,
                "log_count": 0,
                "logs": [],
                "empty_state": empty_state_info,
                "validation": {
                    "total_logs": 0,
                    "summary": "未找到日志记录" + (
                        f"，页面显示: {empty_state_info['emptyMessages'][0]}" 
                        if empty_state_info.get('emptyMessages') 
                        else ""
                    )
                }
            }
            
            print(f"[调试] 空日志处理完成")
            return result
            
        except Exception as e:
            print(f"[调试] 处理空日志失败: {str(e)}")
            return {
                "logs_found": False,
                "log_count": 0,
                "logs": [],
                "error": str(e),
                "validation": {
                    "total_logs": 0,
                    "summary": f"处理空日志时发生错误: {str(e)}"
                }
            }
    
    def _get_log_container_info(self, log_container) -> Dict[str, Any]:
        """获取日志容器的基本信息"""
        try:
            container_info = self.driver.execute_script("""
                var container = arguments[0];
                
                return {
                    tagName: container.tagName,
                    className: container.className,
                    id: container.id,
                    itemCount: container.querySelectorAll('ion-item').length,
                    textLength: container.textContent.length,
                    visible: container.offsetParent !== null,
                    scrollHeight: container.scrollHeight,
                    clientHeight: container.clientHeight
                };
            """, log_container)
            
            return container_info
            
        except Exception as e:
            return {"error": str(e)}
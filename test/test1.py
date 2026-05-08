from playwright.sync_api import sync_playwright

def login_to_website(url, username, password):
    with sync_playwright() as p:
        # 启动无头浏览器
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 导航到登录页面
        page.goto(url)

        # 等待用户名和密码输入框加载完成
        page.wait_for_selector("input[name='username']")
        page.wait_for_selector("input[name='password']")

        # 输入用户名和密码
        page.fill("input[name='username']", username)
        page.fill("input[name='password']", password)

        # 点击登录按钮
        page.click("button[type='submit']")

        # 等待登录后的页面加载完成
        page.wait_for_load_state("networkidle")

        # 验证登录是否成功（可选）
        # 例如，检查某个特定的元素是否存在
        if page.query_selector("#welcome-message"):
            print("登录成功！")
        else:
            print("登录失败！")

        # 关闭浏览器
        browser.close()

# 示例调用
url = "https://www.simuwang.com/"  # 替换为实际的登录页面 URL
username = "your_username"  # 替换为实际的用户名
password = "your_password"  # 替换为实际的密码
login_to_website(url, username, password)

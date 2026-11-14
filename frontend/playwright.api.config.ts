import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./tests-api',workers:1,timeout:90000,
  use:{baseURL:'http://127.0.0.1:8000',browserName:'chromium',launchOptions:{executablePath:process.env.PLAYWRIGHT_CHROME_PATH??'C:/Program Files/Google/Chrome/Application/chrome.exe'},viewport:{width:1440,height:1000},trace:'retain-on-failure'},
  reporter:[['list']],outputDir:'test-results-api',
  webServer:{command:'..\\backend\\.venv\\Scripts\\python.exe ..\\.local\\app_browser_server.py',url:'http://127.0.0.1:8000/api/v1/health',reuseExistingServer:false,timeout:60000},
});

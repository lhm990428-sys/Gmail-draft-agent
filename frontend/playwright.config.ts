import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir:'./tests',fullyParallel:false,workers:1,timeout:30000,
  use:{baseURL:'http://127.0.0.1:5173',browserName:'chromium',launchOptions:{executablePath:process.env.PLAYWRIGHT_CHROME_PATH??'C:/Program Files/Google/Chrome/Application/chrome.exe'},viewport:{width:1440,height:1000},trace:'retain-on-failure'},
  reporter:[['list'],['html',{open:'never'}]],
  webServer:{command:'npm run dev',url:'http://127.0.0.1:5173',reuseExistingServer:!process.env.CI,timeout:60000},
});

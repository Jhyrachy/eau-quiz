import { chromium } from 'playwright';

const CHROME = "/opt/hermes/.playwright/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell";
const url = process.argv[2] || "https://uroweb.org/guidelines/prostate-cancer/chapter/diagnostic-evaluation";

const browser = await chromium.launch({
  executablePath: CHROME,
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
});
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
await page.waitForTimeout(3000);

const headings = await page.evaluate(() => {
  return Array.from(document.querySelectorAll("h2[id], h3[id], h4[id]"))
    .map(el => ({ id: el.id, tag: el.tagName, level: parseInt(el.tagName[1]), text: el.innerText.substring(0, 80) }));
});

console.log(JSON.stringify({ url, headings }, null, 2));
await browser.close();

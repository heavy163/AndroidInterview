#!/usr/bin/env node
/**
 * 简历 MD → 精美 PDF 生成器
 * 用法: node scripts/build_resume_pdf.js
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const PROJECT = '/mnt/e/workspace/AndroidJob';
const MD_FILE = path.join(PROJECT, 'resume_ai_simple.md');
const HTML_FILE = path.join(PROJECT, 'resume_ai_simple.html');
const PDF_FILE = path.join(PROJECT, 'resume_ai_simple.pdf');

// ─── 1. 读取 markdown ───
let md = fs.readFileSync(MD_FILE, 'utf-8');

// ─── 2. 手写 markdown→HTML 转换（核心内容，不依赖外部库） ───
function md2html(text) {
  let html = text;

  // 标题
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // 分割线
  html = html.replace(/^---$/gm, '<hr>');

  // 粗体
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // 链接
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Emoji
  html = html.replace(/📌/g, '<span class="badge">📌</span>');
  html = html.replace(/🤖/g, '🤖');
  html = html.replace(/🖥️/g, '🖥️');
  html = html.replace(/📱/g, '📱');

  // 表格（简化处理：按行解析 | 分隔）
  html = html.replace(/\|(.+)\|/g, (match) => {
    const cells = match.split('|').filter(c => c.trim());
    const isHeader = cells.some(c => /^:?-{3,}:?$/.test(c.trim()));
    if (isHeader) return ''; // 跳过分隔行
    const tag = /^\|(.+)+\|[\s\S]*?\|[-\s|]+\|/.test(match) ? 'th' : 'td';
    return '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>';
  });

  // 列表项
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');

  // 嵌套列表（缩进的）
  html = html.replace(/^  - (.+)$/gm, '<li class="sub">$1</li>');

  // 将连续 <li> 包裹在 <ul> 中
  html = html.replace(/((?:<li[^>]*>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

  // 段落：空行分隔的文本块
  const lines = html.split('\n');
  const result = [];
  let inParagraph = false;
  let paraLines = [];

  for (const line of lines) {
    const trimmed = line.trim();
    // 跳过已处理的标签行
    if (/^<\/?(h[1-3]|hr|ul|li|tr|table|strong|code|a|span|div|img|br)/.test(trimmed) ||
        /^<tr>/.test(trimmed) || /^<th>/.test(trimmed) || /^<td>/.test(trimmed)) {
      if (inParagraph) {
        result.push('<p>' + paraLines.join('<br>') + '</p>');
        inParagraph = false;
        paraLines = [];
      }
      result.push(line);
      continue;
    }
    // 空行 → 段落结束
    if (trimmed === '') {
      if (inParagraph) {
        result.push('<p>' + paraLines.join('<br>') + '</p>');
        inParagraph = false;
        paraLines = [];
      }
      continue;
    }
    // 普通文本
    inParagraph = true;
    paraLines.push(trimmed);
  }
  if (inParagraph) {
    result.push('<p>' + paraLines.join('<br>') + '</p>');
  }

  return result.join('\n');
}

// ─── 3. 生成精美 HTML ───
const bodyHTML = md2html(md);

const fullHTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>占海飞 — 高级安卓应用工程师</title>
<style>
  @page {
    size: A4;
    margin: 18mm 16mm 18mm 16mm;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
    font-size: 11pt;
    line-height: 1.65;
    color: #1a1a1a;
    max-width: 210mm;
    margin: 0 auto;
  }
  h1 {
    font-size: 22pt;
    font-weight: 700;
    text-align: center;
    margin-bottom: 4pt;
    letter-spacing: 2pt;
    color: #111;
  }
  h2 {
    font-size: 12.5pt;
    font-weight: 700;
    color: #1a56db;
    border-bottom: 1.5px solid #1a56db;
    padding-bottom: 3pt;
    margin: 14pt 0 8pt 0;
    letter-spacing: 0.5pt;
  }
  h3 {
    font-size: 11pt;
    font-weight: 600;
    color: #333;
    margin: 8pt 0 4pt 0;
  }
  hr { border: none; border-top: 0.5px solid #ddd; margin: 8pt 0; }
  p { margin: 2pt 0; }
  ul { padding-left: 16pt; margin: 3pt 0; list-style: disc; }
  li { margin: 1.5pt 0; font-size: 10.5pt; }
  li.sub { list-style: circle; margin-left: 8pt; font-size: 10pt; }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 4pt 0;
    font-size: 10.5pt;
  }
  td, th {
    padding: 3pt 6pt;
    text-align: left;
    vertical-align: top;
  }
  td:first-child, th:first-child { font-weight: 600; color: #555; width: 90pt; }
  strong { color: #111; }
  a { color: #1a56db; text-decoration: none; }
  code {
    background: #f0f4ff;
    padding: 1pt 4pt;
    border-radius: 2pt;
    font-size: 9.5pt;
    font-family: "SF Mono", "Consolas", monospace;
  }
  .badge { margin-right: 2pt; }
  .company {
    font-weight: 600;
    color: #333;
    margin-top: 8pt;
  }
  .date {
    color: #888;
    font-size: 10pt;
    font-style: italic;
    margin-bottom: 4pt;
  }
  .highlight {
    font-weight: 600;
    color: #1a56db;
  }
  /* 两栏布局 */
  .contact-table td { padding: 2pt 10pt 2pt 0; }
  .contact-table td:first-child { width: 70pt; }
</style>
</head>
<body>
${bodyHTML}
</body>
</html>`;

fs.writeFileSync(HTML_FILE, fullHTML, 'utf-8');
console.log('✅ HTML 生成:', HTML_FILE);

// ─── 4. 尝试用 Chrome/Edge 打印 PDF ───
function tryPrintPDF() {
  const chromePaths = [
    '/mnt/c/Program Files/Google/Chrome/Application/chrome.exe',
    '/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    '/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    '/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe',
  ];

  for (const chromePath of chromePaths) {
    if (fs.existsSync(chromePath)) {
      console.log('🔍 找到浏览器:', chromePath);
      try {
        const cmd = `"${chromePath}" --headless --disable-gpu --print-to-pdf="${PDF_FILE}" --no-margins "${HTML_FILE}"`;
        execSync(cmd, { timeout: 15000, stdio: 'pipe' });
        if (fs.existsSync(PDF_FILE)) {
          console.log('✅ PDF 生成成功:', PDF_FILE);
          console.log('   大小:', (fs.statSync(PDF_FILE).size / 1024).toFixed(0), 'KB');
          return true;
        }
      } catch (e) {
        console.log('   Chrome 打印失败:', e.message?.slice(0, 80));
      }
    }
  }
  return false;
}

if (!tryPrintPDF()) {
  console.log('\n⚠️  未找到 Chrome/Edge，无法自动生成 PDF。');
  console.log('   💡 请手动操作：');
  console.log('      1. 在浏览器打开:', HTML_FILE);
  console.log('      2. Ctrl+P → 另存为 PDF');
  console.log('      3. 边距设为"无"，勾选"背景图形"');
}

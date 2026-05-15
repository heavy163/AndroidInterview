#!/usr/bin/env node
/**
 * 简历 HTML 生成器 — 完整解析 markdown 表格、列表、格式
 */
const fs = require('fs');
const PROJECT = '/mnt/e/workspace/AndroidJob';
const md = fs.readFileSync(PROJECT + '/resume_ai_simple.md', 'utf-8');

// ─── Markdown → HTML 解析器 ───
function parseMD(text) {
  const lines = text.split('\n');
  const html = [];
  let i = 0;

  function peek() { return i < lines.length ? lines[i] : ''; }
  function next() { return lines[i++]; }
  function isHR(line) { return /^---\s*$/.test(line); }
  function isH1(line) { return /^# (.+)/.test(line); }
  function isH2(line) { return /^## (.+)/.test(line); }
  function isH3(line) { return /^### (.+)/.test(line); }
  function isUL(line) { return /^- (.+)/.test(line); }
  function isSubUL(line) { return /^  - (.+)/.test(line); }
  function isTableSep(line) { return /^\|[-:\s|]+\|$/.test(line); }
  function isTableRow(line) { return /^\|.+\|$/.test(line); }
  function isBlank(line) { return /^\s*$/.test(line); }

  function inline(s) {
    return s
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
      .replace(/📌/g, '<span class="badge">📌</span>');
  }

  function parseTable() {
    // Header row
    const header = next();
    next(); // skip separator
    const cells = header.split('|').filter(c => c.trim());
    let t = '<table><thead><tr>' + cells.map(c => `<th>${inline(c.trim())}</th>`).join('') + '</tr></thead><tbody>';
    while (i < lines.length && isTableRow(peek())) {
      const row = next();
      const rcs = row.split('|').filter(c => c.trim());
      t += '<tr>' + rcs.map(c => `<td>${inline(c.trim())}</td>`).join('') + '</tr>';
    }
    t += '</tbody></table>';
    return t;
  }

  function parseList() {
    let items = '';
    while (i < lines.length && (isUL(peek()) || isSubUL(peek()))) {
      const line = next();
      if (isSubUL(line)) {
        items += `<li class="sub">${inline(line.match(/^  - (.+)/)[1])}</li>`;
      } else {
        items += `<li>${inline(line.match(/^- (.+)/)[1])}</li>`;
      }
    }
    return `<ul>${items}</ul>`;
  }

  while (i < lines.length) {
    const line = peek();
    if (isBlank(line)) { next(); continue; }
    if (isHR(line)) { html.push('<hr>'); next(); continue; }
    if (isH1(line)) { html.push(`<h1>${inline(line.match(/^# (.+)/)[1])}</h1>`); next(); continue; }
    if (isH2(line)) { html.push(`<h2>${inline(line.match(/^## (.+)/)[1])}</h2>`); next(); continue; }
    if (isH3(line)) { html.push(`<h3>${inline(line.match(/^### (.+)/)[1])}</h3>`); next(); continue; }
    if (isTableRow(line) && i+1 < lines.length && isTableSep(lines[i+1])) {
      html.push(parseTable()); continue;
    }
    if (isUL(line)) { html.push(parseList()); continue; }
    // Paragraph
    let para = inline(next().trim());
    while (i < lines.length && !isBlank(peek()) && !isHR(peek()) && !isH1(peek()) && !isH2(peek()) && !isH3(peek()) && !isUL(peek()) && !isTableRow(peek()) && !isTableSep(peek())) {
      para += '<br>' + inline(next().trim());
    }
    html.push(`<p>${para}</p>`);
  }
  return html.join('\n');
}

const body = parseMD(md);

const fullHTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>占海飞 — 高级安卓应用工程师</title>
<style>
  @page { size: A4; margin: 15mm 14mm 15mm 14mm; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
    font-size: 10.5pt;
    line-height: 1.6;
    color: #1a1a1a;
    max-width: 210mm;
    margin: 0 auto;
  }
  h1 {
    font-size: 20pt;
    font-weight: 700;
    text-align: center;
    margin-bottom: 3pt;
    letter-spacing: 2pt;
    color: #111;
  }
  h2 {
    font-size: 12pt;
    font-weight: 700;
    color: #1a56db;
    border-bottom: 1.5px solid #1a56db;
    padding-bottom: 2pt;
    margin: 12pt 0 6pt 0;
    letter-spacing: 0.5pt;
  }
  h3 {
    font-size: 10.5pt;
    font-weight: 600;
    color: #333;
    margin: 7pt 0 3pt 0;
  }
  hr { border: none; border-top: 0.5px solid #ddd; margin: 6pt 0; }
  p { margin: 2pt 0; font-size: 10pt; }
  ul { padding-left: 14pt; margin: 2pt 0 5pt 0; list-style: disc; }
  li { margin: 1.5pt 0; font-size: 10pt; }
  li.sub { list-style: circle; margin-left: 8pt; font-size: 9.5pt; }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 4pt 0;
    font-size: 10pt;
  }
  thead { display: none; }
  td, th {
    padding: 2pt 6pt;
    text-align: left;
    vertical-align: top;
  }
  td:first-child { font-weight: 600; color: #555; width: 85pt; white-space: nowrap; }
  strong { color: #111; }
  a { color: #1a56db; text-decoration: none; }
  code {
    background: #f0f4ff;
    padding: 1pt 3pt;
    border-radius: 2pt;
    font-size: 9pt;
    font-family: "Consolas", "SF Mono", monospace;
  }
  .badge { margin-right: 2pt; }
</style>
</head>
<body>
${body}
</body>
</html>`;

fs.writeFileSync(PROJECT + '/resume_ai_simple.html', fullHTML, 'utf-8');
console.log('✅ HTML 重新生成: ' + (fullHTML.length / 1024).toFixed(0) + 'KB');

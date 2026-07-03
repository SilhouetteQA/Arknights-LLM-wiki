/* PRTS Archive -- SSE 流式对话客户端 */
var $ = function(sel) { return document.querySelector(sel); };
var chatMessages = $('#chat-messages');
var emptyState = $('#empty-state');
var searchSteps = $('#search-steps');
var panelEmpty = $('#panel-empty');
var panelFooter = $('#panel-footer');
var questionInput = $('#question-input');
var sendBtn = $('#send-btn');
var statusText = $('#status-text');
var statusLatency = $('#status-latency');
var statusTokens = $('#status-tokens');

var currentAnswerCard = null;
var currentAnswerSpan = null;
var currentAnswerText = '';
var stepCount = 0;
var tokenCount = 0;
var isLoading = false;

/* ---- 智能滚动：仅在用户已在底部时自动滚动 ---- */
function shouldAutoScroll(el) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 60;
}
function scrollChat() {
  if (shouldAutoScroll(chatMessages)) {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
}
function scrollSteps() { searchSteps.scrollTop = searchSteps.scrollHeight; }

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ---- 回答文本格式化 ---- */
function formatAnswerText(text) {
  if (!text) return '';
  var html = escapeHtml(text);
  // 粗体 **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // 标题行: 以 # 或 ## 开头的行
  html = html.replace(/^(#{1,2})\s+(.+)$/gm, function(match, hashes, content) {
    return '<span class="answer-heading">' + content + '</span>';
  });
  // 分隔线 ---
  html = html.replace(/^---+\s*$/gm, '<span class="answer-hr"></span>');
  // 双换行 → 段落分隔
  html = html.replace(/\n\n+/g, '</p><p>');
  // 单换行 → <br>
  html = html.replace(/\n/g, '<br>');
  return '<p>' + html + '</p>';
}

/* ---- 聊天区消息渲染 ---- */

function addUserMessage(text) {
  if (emptyState) { emptyState.remove(); emptyState = null; }
  var div = document.createElement('div');
  div.className = 'msg-user';
  div.textContent = text;
  chatMessages.appendChild(div);
  scrollChat();
}

function addRouteInfo(route) {
  var div = document.createElement('div');
  div.className = 'msg-route';
  div.innerHTML =
    '<span class="route-label">[路由]</span> ' + escapeHtml(route.complexity || '') +
    ' <span class="route-sep">|</span> ' +
    '<span class="route-label">[意图]</span> ' + escapeHtml(route.question_type || '') +
    ' <span class="route-sep">|</span> ' +
    '<span class="route-label">[实体]</span> ' + escapeHtml((route.entities || []).join(', '));
  chatMessages.appendChild(div);
  scrollChat();
}

function createAnswerCard() {
  var card = document.createElement('div');
  card.className = 'msg-answer streaming';
  // 复制按钮
  var copyBtn = document.createElement('button');
  copyBtn.className = 'answer-copy-btn';
  copyBtn.textContent = 'COPY';
  copyBtn.onclick = function() {
    navigator.clipboard.writeText(currentAnswerText || '').then(function() {
      copyBtn.textContent = 'COPIED';
      setTimeout(function() { copyBtn.textContent = 'COPY'; }, 1500);
    });
  };
  card.appendChild(copyBtn);
  // 文本容器
  var span = document.createElement('span');
  span.className = 'answer-text';
  card.appendChild(span);
  chatMessages.appendChild(card);
  return { card: card, span: span };
}

function appendToken(text) {
  if (!currentAnswerSpan) {
    var created = createAnswerCard();
    currentAnswerCard = created.card;
    currentAnswerSpan = created.span;
    currentAnswerText = '';
  }
  currentAnswerText += text;
  currentAnswerSpan.innerHTML = formatAnswerText(currentAnswerText);
  scrollChat();
}

function finishAnswer() {
  if (currentAnswerCard) {
    currentAnswerCard.classList.remove('streaming');
    currentAnswerSpan.innerHTML = formatAnswerText(currentAnswerText);
  }
  currentAnswerCard = null;
  currentAnswerSpan = null;
  currentAnswerText = '';
}

/* ---- 检索面板 ---- */

function clearSteps() {
  if (panelEmpty) { panelEmpty.remove(); panelEmpty = null; }
  var cards = searchSteps.querySelectorAll('.step-card');
  for (var i = 0; i < cards.length; i++) { cards[i].remove(); }
  stepCount = 0;
}

function addStepCard(label, labelClass, detailHtml, timing) {
  stepCount++;
  var card = document.createElement('div');
  card.className = 'step-card';
  card.innerHTML =
    '<div class="step-label ' + (labelClass || '') + '">[' + stepCount + '] ' + escapeHtml(label) + '</div>' +
    '<div class="step-detail">' + detailHtml + '</div>' +
    (timing ? '<div class="step-timing">' + escapeHtml(timing) + '</div>' : '');
  searchSteps.appendChild(card);
  scrollSteps();
}

function showSources(sources) {
  var html = '';
  sources.forEach(function(s) {
    html += '<div class="source-item">' +
      '[<span class="source-idx">' + s.ref + '</span>] ' +
      '<span class="source-type">' + escapeHtml(s.tool || s.entity_type || '') + ':</span> ' +
      escapeHtml(s.name || s.summary || '') +
      '</div>';
  });
  addStepCard('SOURCES', 'sources', html, null);
  panelFooter.textContent = '共计 ' + sources.length + ' 个来源';
}

/* ---- SSE 事件分发 ---- */

function handleSSE(event, data) {
  switch (event) {
    case 'route':
      addRouteInfo(data);
      addStepCard('ROUTE', 'route',
        escapeHtml(data.complexity || '') + ' / ' + escapeHtml(data.question_type || '') +
        '<br><span class="dim">entities: ' + escapeHtml((data.entities || []).join(', ')) + '</span>',
        null);
      break;
    case 'token':
      tokenCount++;
      statusTokens.textContent = 'Tokens: ' + tokenCount;
      appendToken(data.text || '');
      break;
    case 'step':
      addStepCard(data.tool || 'STEP', 'semantic',
        escapeHtml(data.summary || ''), null);
      break;
    case 'sources':
      if (Array.isArray(data)) showSources(data);
      break;
    case 'done':
      finishAnswer();
      panelFooter.textContent = '共计 ' + (data.total_steps || 0) + ' 个步骤';
      break;
  }
}

/* ---- 错误消息 ---- */

function showError(msg) {
  var div = document.createElement('div');
  div.className = 'msg-error';
  div.textContent = '[错误] ' + msg;
  chatMessages.appendChild(div);
  scrollChat();
}

/* ---- 主流程 ---- */

async function ask() {
  var question = questionInput.value.trim();
  if (!question || isLoading) return;

  addUserMessage(question);
  questionInput.value = '';
  isLoading = true;
  sendBtn.disabled = true;
  statusText.textContent = 'QUERYING';
  statusText.style.color = '#c4a55a';

  currentAnswerCard = null;
  currentAnswerSpan = null;
  currentAnswerText = '';
  stepCount = 0;
  tokenCount = 0;
  clearSteps();

  var startTime = performance.now();

  try {
    var response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: question }),
    });

    if (!response.ok) {
      var errText = 'HTTP ' + response.status;
      try { var errJson = await response.json(); errText = errJson.detail || errText; } catch(e) {}
      showError(errText);
      return;
    }

    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    var currentEvent = '';

    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;

      buffer += decoder.decode(chunk.value, { stream: true });
      var lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          try {
            var data = JSON.parse(line.slice(6));
            handleSSE(currentEvent, data);
            currentEvent = '';
          } catch(e) {}
        } else if (line === '') {
          currentEvent = '';
        }
      }
    }

    var elapsed = Math.round(performance.now() - startTime);
    statusText.textContent = 'READY';
    statusText.style.color = '#6b5d3e';
    statusLatency.textContent = '耗时: ' + elapsed + 'ms';
  } catch (err) {
    statusText.textContent = 'ERROR';
    statusText.style.color = '#c06050';
    showError('请求失败，请重试');
  } finally {
    isLoading = false;
    sendBtn.disabled = false;
    questionInput.focus();
  }
}

sendBtn.addEventListener('click', ask);
questionInput.addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    ask();
  }
});

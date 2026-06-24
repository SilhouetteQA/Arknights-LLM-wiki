/* PRTS 终端 -- SSE 流式对话客户端 */
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

var currentAnswerSpan = null;
var stepCount = 0;
var isLoading = false;

function scrollChat() { chatMessages.scrollTop = chatMessages.scrollHeight; }
function scrollSteps() { searchSteps.scrollTop = searchSteps.scrollHeight; }

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ---- 聊天区消息渲染 ---- */

function addUserMessage(text) {
  if (emptyState) emptyState.remove();
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
    ' <span class="separator">|</span> ' +
    '<span class="route-label">[类别]</span> ' + escapeHtml(route.question_type || '') +
    ' <span class="separator">|</span> ' +
    '<span class="route-label">[实体]</span> ' + escapeHtml((route.entities || []).join(', '));
  chatMessages.appendChild(div);
  scrollChat();
}

function createAnswerCard() {
  var card = document.createElement('div');
  card.className = 'msg-answer';
  var corner = document.createElement('div');
  corner.className = 'corner-tr';
  card.appendChild(corner);
  var span = document.createElement('span');
  span.className = 'answer-text';
  card.appendChild(span);
  chatMessages.appendChild(card);
  return { card: card, span: span };
}

function appendToken(text) {
  if (!currentAnswerSpan) {
    var created = createAnswerCard();
    currentAnswerSpan = created.span;
  }
  currentAnswerSpan.textContent += text;
  scrollChat();
}

/* ---- 检索面板 ---- */

function clearSteps() {
  if (panelEmpty) panelEmpty.remove();
  var cards = searchSteps.querySelectorAll('.step-card');
  for (var i = 0; i < cards.length; i++) { cards[i].remove(); }
  stepCount = 0;
}

function addStepCard(label, labelClass, detailHtml, timing) {
  stepCount++;
  var card = document.createElement('div');
  card.className = 'step-card';
  card.innerHTML =
    '<div class="step-label ' + labelClass + '">[' + stepCount + '] ' + escapeHtml(label) + '</div>' +
    '<div class="step-detail">' + detailHtml + '</div>' +
    (timing ? '<div class="step-timing">' + escapeHtml(timing) + '</div>' : '');
  searchSteps.appendChild(card);
  scrollSteps();
}

function showSources(sources) {
  var detail = '';
  sources.forEach(function(s) {
    detail += '<div class="source-item">' +
      '[<span class="source-idx">' + s.ref + '</span>] ' +
      '<span class="source-type">' + escapeHtml(s.tool || s.entity_type || '') + ':</span> ' +
      escapeHtml(s.name || s.summary || '') +
      '</div>';
  });
  addStepCard('SOURCES', 'sources', detail, null);
  panelFooter.textContent = '总计 ' + sources.length + ' 来源';
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
      panelFooter.textContent = '总计 ' + (data.total_steps || 0) + ' 步骤';
      break;
  }
}

/* ---- 主流程 ---- */

async function ask() {
  var question = questionInput.value.trim();
  if (!question || isLoading) return;

  addUserMessage(question);
  questionInput.value = '';
  isLoading = true;
  sendBtn.disabled = true;
  statusText.textContent = 'QUERYING...';
  statusText.style.color = '#ffb000';

  currentAnswerSpan = null;
  stepCount = 0;
  clearSteps();

  var startTime = performance.now();

  try {
    var response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: question }),
    });

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
    statusText.style.color = '#4fc3f7';
    statusLatency.textContent = 'Latency: ' + elapsed + 'ms';
  } catch (err) {
    statusText.textContent = 'ERROR';
    statusText.style.color = '#ff4444';
  } finally {
    isLoading = false;
    sendBtn.disabled = false;
    questionInput.focus();
  }
}

sendBtn.addEventListener('click', ask);
questionInput.addEventListener('keydown', function(e) {
  if (e.key === 'Enter') ask();
});

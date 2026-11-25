/* ask.js - the Ask Hawa chat.
   The conversation lives only in this page (it is gone when you reload);
   the last few turns are sent along so Ask Hawa understands follow-up questions. */

var log = document.getElementById("chat-log");
var form = document.getElementById("chat-form");
var input = document.getElementById("question");
var sendBtn = document.getElementById("send-btn");
var chatHistory = []; // [{role: "user" | "model", text: "..."}] (not called "history": that name belongs to the browser)
var busy = false;

/** Safe formatting: escape everything, then allow **bold** and line breaks. */
function format(text) {
  return Hawa.esc(text)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/^\s*[-*] /gm, "• ")
    .replace(/\n/g, "<br>");
}

function addMessage(kind, text) {
  var div = document.createElement("div");
  div.className = "msg " + kind;
  div.innerHTML = format(text);
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function ask(question) {
  question = question.trim();
  if (!question || busy) return;
  if (question.length > window.ASK_MAX) {
    addMessage("bot error", "Please keep questions under " + window.ASK_MAX + " characters.");
    return;
  }
  busy = true;
  sendBtn.disabled = true;
  input.value = "";
  addMessage("user", question);
  var typing = addMessage("bot typing", "Ask Hawa is thinking…");

  fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: question, history: chatHistory.slice(-6) }),
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      typing.remove();
      if (data.ok) {
        addMessage("bot", data.answer);
        chatHistory.push({ role: "user", text: question }, { role: "model", text: data.answer });
      } else {
        addMessage("bot error", data.error || "Something went wrong.");
      }
    })
    .catch(function () {
      typing.remove();
      addMessage("bot error", "Couldn't reach the server. Please try again.");
    })
    .finally(function () {
      busy = false;
      sendBtn.disabled = false;
      input.focus();
    });
}

form.addEventListener("submit", function (e) {
  e.preventDefault();
  ask(input.value);
});

// Enter sends, Shift+Enter makes a new line
input.addEventListener("keydown", function (e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    ask(input.value);
  }
});

// Suggestion buttons
document.querySelectorAll("#suggestions button").forEach(function (btn) {
  btn.addEventListener("click", function () { ask(btn.textContent); });
});

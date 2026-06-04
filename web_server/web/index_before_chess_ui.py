<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>Mirobot Web Controller</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      padding: 30px;
      background: #f5f5f5;
    }

    h1 {
      margin-bottom: 5px;
    }

    .board {
      display: grid;
      grid-template-columns: repeat(3, 90px);
      grid-template-rows: repeat(3, 90px);
      gap: 8px;
      margin: 20px 0;
    }

    .cell {
      font-size: 24px;
      font-weight: bold;
      border: 2px solid #333;
      border-radius: 10px;
      background: white;
      cursor: pointer;
    }

    .cell.selected {
      background: #ffe08a;
    }

    .panel {
      background: white;
      padding: 15px;
      border-radius: 10px;
      width: 320px;
    }

    button {
      padding: 10px 16px;
      font-size: 16px;
      cursor: pointer;
      margin-top: 10px;
    }

    #log {
      margin-top: 20px;
      white-space: pre-wrap;
      background: #222;
      color: #eee;
      padding: 15px;
      border-radius: 10px;
      width: 600px;
      min-height: 120px;
    }
  </style>
</head>
<body>
  <h1>Mirobot Web Controller</h1>
  <p>출발 칸 → 도착 칸 순서로 누르고 Move 버튼 누르셈.</p>

  <div class="board">
    <button class="cell" data-cell="A3">A3</button>
    <button class="cell" data-cell="B3">B3</button>
    <button class="cell" data-cell="C3">C3</button>

    <button class="cell" data-cell="A2">A2</button>
    <button class="cell" data-cell="B2">B2</button>
    <button class="cell" data-cell="C2">C2</button>

    <button class="cell" data-cell="A1">A1</button>
    <button class="cell" data-cell="B1">B1</button>
    <button class="cell" data-cell="C1">C1</button>
  </div>

  <div class="panel">
    <div>Start: <span id="start">없음</span></div>
    <div>End: <span id="end">없음</span></div>
    <button onclick="sendMove()">Move</button>
    <button onclick="resetSelection()">Reset</button>
  </div>

  <div id="log">log...</div>

  <script>
    let start = null;
    let end = null;

    const startSpan = document.getElementById("start");
    const endSpan = document.getElementById("end");
    const log = document.getElementById("log");

    document.querySelectorAll(".cell").forEach(btn => {
      btn.addEventListener("click", () => {
        const cell = btn.dataset.cell;

        if (start === null) {
          start = cell;
          startSpan.textContent = start;
          btn.classList.add("selected");
        } else if (end === null) {
          end = cell;
          endSpan.textContent = end;
          btn.classList.add("selected");
        } else {
          resetSelection();
          start = cell;
          startSpan.textContent = start;
          btn.classList.add("selected");
        }
      });
    });

    function resetSelection() {
      start = null;
      end = null;
      startSpan.textContent = "없음";
      endSpan.textContent = "없음";

      document.querySelectorAll(".cell").forEach(btn => {
        btn.classList.remove("selected");
      });

      log.textContent = "reset";
    }

    async function sendMove() {
      if (!start || !end) {
        alert("출발 칸이랑 도착 칸 둘 다 선택하셈");
        return;
      }

      log.textContent = `moving ${start} -> ${end} ...`;

      try {
        const res = await fetch("/move", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            start: start,
            end: end,
          }),
        });

        const data = await res.json();

        if (!res.ok) {
          log.textContent = "ERROR\n" + JSON.stringify(data, null, 2);
          return;
        }

        log.textContent = "SUCCESS\n" + JSON.stringify(data, null, 2);
      } catch (err) {
        log.textContent = "FETCH ERROR\n" + err;
      }
    }
  </script>
</body>
</html>

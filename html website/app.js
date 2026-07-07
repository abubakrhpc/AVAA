// ── Pi connection ─────────────────────────────────────────────
const PI_IP      = '10.249.89.50';  // ← update if IP changes
const API        = `http://${PI_IP}:5000`;
const STREAM_URL = `${API}/video`;   // camera on SAME port 5000
const LAPTOP_IP = '10.249.89.171'; // your Linux laptop IP
const LAPTOP_API = `http://${LAPTOP_IP}:5002`;

// ── home / aruco ──────────────────────────────────────────────
document.getElementById('homeBtn').addEventListener('click', () => {
  fetch(`${LAPTOP_API}/go_home`, { method: 'POST' })
    .then(() => prependAlert('🏠 Home mode — AVAA returning to dock.'))
    .catch(() => prependAlert('Cannot reach laptop server.'));
});

// ── DOM refs ──────────────────────────────────────────────────
const navLinks      = document.querySelectorAll('.nav-link');
const pages         = document.querySelectorAll('.page');
const statusBadge   = document.getElementById('statusBadge');
const alertsList    = document.getElementById('alertsList');
const cameraImg     = document.getElementById('cameraImg');
const cameraOff     = document.getElementById('cameraOff');
const systemMessage = document.getElementById('systemMessage');
const startBtn      = document.getElementById('startBtn');
const stopBtn       = document.getElementById('stopBtn');
const emergencyBtn  = document.getElementById('emergencyBtn');
const followerBtn   = document.getElementById('followerBtn');
const talkBtn       = document.getElementById('talkBtn');
const avaMessage    = document.getElementById('avaMessage');
const heroRobotImage    = document.getElementById('heroRobotImage');
const aboutRobotImage   = document.getElementById('aboutRobotImage');
const robotFallbackText = document.getElementById('robotFallbackText');
const characterDock     = document.getElementById('characterDock');

// ── state ─────────────────────────────────────────────────────
let monitoringActive = false;

// ── nav ───────────────────────────────────────────────────────
function showPage(pageId) {
  pages.forEach(p => p.classList.remove('active'));
  navLinks.forEach(l => l.classList.remove('active'));
  document.getElementById(pageId).classList.add('active');
  document.querySelector(`[data-page="${pageId}"]`).classList.add('active');
}
navLinks.forEach(link => link.addEventListener('click', () => showPage(link.dataset.page)));

// ── status badge ──────────────────────────────────────────────
function setStatus(level) {
  const map = { safe: '✅ Safe', warning: '⚠️ Warning', alert: '🛑 Alert' };
  statusBadge.textContent = map[level] || '✅ Safe';
  statusBadge.classList.remove('safe', 'warning', 'alert');
  statusBadge.classList.add(level);
}

// ── alerts ────────────────────────────────────────────────────
function prependAlert(message) {
  const item = document.createElement('li');
  item.className = 'alert-item';
  const time = new Date().toLocaleTimeString();
  item.innerHTML = `<span class="alert-time">${time}</span><span class="alert-text">${message}</span>`;
  alertsList.prepend(item);
  while (alertsList.children.length > 7) alertsList.removeChild(alertsList.lastChild);
}

// ── start monitoring (camera only) ───────────────────────────
startBtn.addEventListener('click', () => {
  fetch(`${API}/start_camera`, { method: 'POST' })
    .then(() => {
      prependAlert('Camera starting...');
      setTimeout(() => {
        cameraImg.src = STREAM_URL + '?t=' + Date.now();
        cameraImg.hidden = false;
        if (cameraOff) cameraOff.hidden = true;
        setStatus('safe');
        prependAlert('Live camera feed active.');
        monitoringActive = true;
      }, 3000);
    })
    .catch(() => prependAlert('Cannot reach robot — is controller running?'));
});

// ── stop monitoring ───────────────────────────────────────────
stopBtn.addEventListener('click', () => {
  fetch(`${API}/stop_camera`,   { method: 'POST' }).catch(() => {});
  fetch(`${API}/stop_follower`, { method: 'POST' }).catch(() => {});
  cameraImg.src = '';
  cameraImg.hidden = true;
  if (cameraOff) cameraOff.hidden = false;
  setStatus('safe');
  prependAlert('Camera and follower stopped.');
  monitoringActive = false;
});

// ── emergency stop ────────────────────────────────────────────
emergencyBtn.addEventListener('click', () => {
  fetch(`${API}/emergency_stop`, { method: 'POST' })
    .then(() => {
      cameraImg.src = '';
      cameraImg.hidden = true;
      if (cameraOff) cameraOff.hidden = false;
      systemMessage.textContent = '🛑 ROBOT STOPPED.';
      prependAlert('Emergency stop — robot halted!');
      setStatus('alert');
      monitoringActive = false;
    })
    .catch(() => {
      systemMessage.textContent = '🛑 Emergency stop sent.';
      setStatus('alert');
      prependAlert('Emergency stop sent (robot may be offline).');
    });
});

// ── start follower ────────────────────────────────────────────
followerBtn.addEventListener('click', () => {
  fetch(`${API}/start_follower`, { method: 'POST' })
    .then(() => prependAlert('Follower started — AVAA is following!'))
    .catch(() => prependAlert('Cannot reach robot.'));
});

// ── companion talk ────────────────────────────────────────────
const talkMessages = ["Let's play!", 'Stay safe!', "I'm here with you!"];
talkBtn.addEventListener('click', () => {
  const randomMessage = talkMessages[Math.floor(Math.random() * talkMessages.length)];
  avaMessage.textContent = randomMessage;
});

// ── robot image probe ─────────────────────────────────────────
function setupRobotImage() {
  const candidates = ['avaa.png','robot.png','robot.jpg','robot.jpeg','robot.webp'];
  const probe = new Image();
  let i = 0;
  function tryNext() {
    if (i >= candidates.length) {
      if (heroRobotImage)    heroRobotImage.hidden = true;
      if (aboutRobotImage)   aboutRobotImage.hidden = true;
      if (robotFallbackText) robotFallbackText.hidden = false;
      return;
    }
    probe.src = `${candidates[i]}?v=${Date.now()}`;
    probe.onload = () => {
      if (heroRobotImage)  { heroRobotImage.hidden = false;  heroRobotImage.src  = candidates[i]; }
      if (aboutRobotImage) { aboutRobotImage.hidden = false; aboutRobotImage.src = candidates[i]; }
      if (robotFallbackText) robotFallbackText.hidden = true;
    };
    probe.onerror = () => { i++; tryNext(); };
  }
  tryNext();
}

// ── cute character popups ─────────────────────────────────────
const cuteCharacters = [
  { icon: '🐻', name: 'Bobo',   message: 'Hi friend!'            },
  { icon: '🐰', name: 'Luna',   message: 'You are doing great!'  },
  { icon: '🐱', name: 'Mimi',   message: 'Stay safe and smile!'  },
  { icon: '🐼', name: 'Pip',    message: 'Hello hello!'          },
  { icon: '🦊', name: 'Foxy',   message: 'Keep shining!'         },
  { icon: '🐶', name: 'Nugget', message: 'Paw-sitive vibes only!'},
];
function showCuteCharacter() {
  if (!characterDock) return;
  const c = cuteCharacters[Math.floor(Math.random() * cuteCharacters.length)];
  const card = document.createElement('div');
  card.className = 'character-popup';
  card.innerHTML = `<span class="character-icon" aria-hidden="true">${c.icon}</span>
    <div class="character-copy"><strong>${c.name}</strong><span>${c.message}</span></div>`;
  characterDock.innerHTML = '';
  characterDock.appendChild(card);
  requestAnimationFrame(() => card.classList.add('visible'));
  setTimeout(() => {
    card.classList.remove('visible');
    setTimeout(() => { if (characterDock.contains(card)) characterDock.removeChild(card); }, 300);
  }, 3500);
}
function scheduleCuteCharacters() {
  showCuteCharacter();
  setInterval(() => { if (Math.random() > 0.45) showCuteCharacter(); }, 12000);
}

// ── battery polling ───────────────────────────────────────────
function updateBattery() {
  fetch(`${API}/health`)
    .then(r => r.json())
    .then(data => {
      const pct = data.battery || 0;
      const el  = document.getElementById('batteryLevel');
      const bar = document.getElementById('batteryBar');
      if (!el || !bar) return;
      el.textContent = pct + '%';
      bar.style.width = pct + '%';
      bar.style.background = pct > 50
        ? 'var(--sage)'
        : pct > 20
        ? 'var(--accent-3)'
        : 'var(--accent-2)';
    })
    .catch(() => {});
}
setInterval(updateBattery, 5000);
updateBattery();

document.getElementById('resetTargetBtn').addEventListener('click', () => {
  fetch(`${LAPTOP_API}/reset_target`, { method: 'POST' })
    .then(() => prependAlert('Target lock reset — AVAA will lock onto next person seen.'))
    .catch(() => prependAlert('Cannot reach laptop YOLO server.'));
});

// ── init ──────────────────────────────────────────────────────
setupRobotImage();
scheduleCuteCharacters();

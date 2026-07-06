from flask import Flask, jsonify, render_template, request


app = Flask(__name__)

# Simple shared state so the UI can reflect AVAA mode.
avaa_state = {
    "mode": "idle",  # idle | listening | thinking | speaking
    "heard_text": "Say hi to AVAA.",
    "hazard": None,
}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def get_state():
    return jsonify(avaa_state)


@app.post("/api/state")
def set_state():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", avaa_state["mode"])
    heard_text = data.get("heard_text", avaa_state["heard_text"])
    hazard = data.get("hazard", avaa_state["hazard"])

    if mode in {"idle", "listening", "thinking", "speaking"}:
        avaa_state["mode"] = mode
    avaa_state["heard_text"] = str(heard_text)
    # Allows reset (None) or setting to a string class (e.g. "scissors")
    avaa_state["hazard"] = hazard if hazard is not None or "hazard" in data else avaa_state["hazard"]
    
    # Optional shortcut: if a hazard is sent, merge it directly into the state
    if "hazard" in data:
        avaa_state["hazard"] = data["hazard"]
        
    return jsonify({"ok": True, "state": avaa_state})


if __name__ == "__main__":
    # Bind to 0.0.0.0 to allow access from other devices (e.g. laptop connected to Pi)
    app.run(host="0.0.0.0", port=5000, debug=True)


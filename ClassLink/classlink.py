from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, send, join_room, leave_room
from pymongo import MongoClient
import bcrypt
import atexit
from gpt4all import GPT4All


#! --> AI Model <--

gpt_model = GPT4All(r"C:\ClassLink\Local_LLM\Llama-3.2-1B-Instruct-Q4_0.gguf")


#! --> Flask/Socket.IO <--

app = Flask(__name__)
app.secret_key = "lei123"
socketio = SocketIO(app)


#! --> MongoDB Connection <--

client = MongoClient("mongodb://localhost:27017/")
db = client["chat_app"]
users = db["users"]
messages = db["messages"]

# * State
connected_users = {}
active_chats = {}


# * Room generator
def get_room_name(user1, user2):
    return "-".join(sorted([user1, user2]))


#! --> Socket.IO Events <--


# * State
@socketio.on("register")
def register_user(data):
    username = data.get("username")
    sid = request.sid

    if username not in connected_users:
        connected_users[username] = set()
    connected_users[username].add(sid)
    print(f"{username} connected with sid {sid}")


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    for user, sids in list(connected_users.items()):
        if sid in sids:
            sids.remove(sid)
            print(f"{user} disconnected {sid}")
            if not sids:
                connected_users.pop(user)
            break


@socketio.on("join_room")
def handle_join(data):
    room = data["room"]
    join_room(room)
    print(f"{session.get('username')} joined room {room}")


@socketio.on("leave_room")
def handle_leave(data):
    room = data["room"]
    leave_room(room)
    print(f"{session.get('username')} left room {room}")


# * Private chat
@socketio.on("private_message")
def handle_private_message(data):
    recipient_username = data["to"]
    message = data["msg"]
    sender_username = session.get("username", "Anonymous")

    # ? AI
    if recipient_username == "ai_bot":
        print("AI received message:", message)
        with gpt_model.chat_session():
            ai_reply = gpt_model.generate(message, max_tokens=120)

        socketio.emit(
            "private_message",
            {
                "from": "ClassBot",
                "from_username": "ai_bot",
                "to": sender_username,
                "msg": ai_reply,
            },
            room=get_room_name("ai_bot", sender_username),
        )
        return

    # ? User
    sender_user = users.find_one({"username": sender_username})
    sender_fullname = sender_user["fullname"] if sender_user else sender_username

    # ? Database
    messages.insert_one(
        {
            "sender_username": sender_username,
            "sender_fullname": sender_fullname,
            "recipient": recipient_username,
            "msg": message,
            "private": True,
        }
    )

    room = get_room_name(sender_username, recipient_username)
    socketio.emit(
        "private_message",
        {
            "from": sender_fullname,
            "from_username": sender_username,
            "to": recipient_username,
            "msg": message,
        },
        room=room,
    )

    # ? Updater
    for uname, other in [
        (sender_username, recipient_username),
        (recipient_username, sender_username),
    ]:
        u = users.find_one({"username": uname})
        recents = u.get("recent_chats", [])
        if other in recents:
            recents.remove(other)
        recents.insert(0, other)
        users.update_one({"username": uname}, {"$set": {"recent_chats": recents}})

    recipient_online = recipient_username in connected_users
    recipient_viewing_sender = active_chats.get(recipient_username) == sender_username

    if not recipient_online or not recipient_viewing_sender:
        users.update_one(
            {"username": recipient_username},
            {"$addToSet": {"unread_chats": sender_username}},
        )

    if recipient_username in connected_users:
        for sid in connected_users[recipient_username]:
            socketio.emit(
                "recent_chat_update",
                {"username": sender_username, "fullname": sender_fullname},
                room=sid,
            )

    recipient_data = users.find_one({"username": recipient_username})
    if sender_username in connected_users:
        for sid in connected_users[sender_username]:
            socketio.emit(
                "recent_chat_update",
                {
                    "username": recipient_username,
                    "fullname": recipient_data["fullname"],
                },
                room=sid,
            )


# * State
@socketio.on("open_chat")
def handle_open_chat(data):
    username = session.get("username")
    target = data.get("target")
    if username:
        active_chats[username] = target
        print(f"{username} is viewing chat with {target}")


@socketio.on("close_chat")
def handle_close_chat(data):
    username = session.get("username")
    if username and username in active_chats:
        active_chats.pop(username)
        print(f"{username} closed chat")


#! --> Flask Routes <--


# * Intro
@app.route("/")
def index():
    return render_template("index.html")


# * Sign Up
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        fullname = request.form["fullname"]
        password = request.form["password"]
        is_teacher = True if request.form.get("is_teacher") == "yes" else False

        if users.find_one({"username": username}):
            return "Username already exists."

        hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        users.insert_one(
            {
                "username": username,
                "fullname": fullname,
                "password": hashed_pw,
                "is_teacher": is_teacher,
            }
        )

        session["username"] = username
        session["fullname"] = fullname
        session["is_teacher"] = is_teacher

        return redirect(url_for("dashboard"))

    return render_template("signup.html")


# * Login In
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = users.find_one({"username": username})
        if user and bcrypt.checkpw(password.encode("utf-8"), user["password"]):
            session["username"] = username
            session["fullname"] = user["fullname"]
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid username or password."

    return render_template("login.html", error=error)


# * Dashboard
@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    user = users.find_one({"username": session["username"]})
    recent_chat_usernames = user.get("recent_chats", [])

    # ? AI on top
    if "ai_bot" not in recent_chat_usernames:
        recent_chat_usernames.insert(0, "ai_bot")

    unread_chats = list(user.get("unread_chats", []))

    # ? AI (not stored in db)
    ai_user = {"username": "ai_bot", "fullname": "ClassBot"}

    recent_chats = []
    for uname in recent_chat_usernames:
        if uname == "ai_bot":
            recent_chats.append(ai_user)
            continue
        target = users.find_one({"username": uname})
        if target:
            recent_chats.append(
                {"username": target["username"], "fullname": target["fullname"]}
            )

    return render_template(
        "dashboard.html",
        fullname=user["fullname"],
        recent_chats=recent_chats,
        username=user["username"],
        unread_chats=unread_chats,
    )


# * Load messages state
@app.route("/mark_read/<username>", methods=["POST"])
def mark_read(username):
    if "username" not in session:
        return "Unauthorized", 401

    current_user = session["username"]
    users.update_one({"username": current_user}, {"$pull": {"unread_chats": username}})
    return "OK"


# * Profile
@app.route("/profile")
def profile():
    if "username" not in session:
        return redirect(url_for("login"))

    user = users.find_one({"username": session["username"]})
    return render_template(
        "profile.html",
        fullname=user["fullname"],
        username=user["username"],
        is_teacher=user.get("is_teacher", False),
    )


# * Log Out
@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("fullname", None)
    return redirect(url_for("index"))


# * Search
@app.route("/search_user")
def search_user():
    query = request.args.get("query", "")
    result = list(
        users.find(
            {
                "$or": [
                    {"fullname": {"$regex": query, "$options": "i"}},
                    {"username": {"$regex": query, "$options": "i"}},
                ]
            },
            {"_id": 0, "username": 1, "fullname": 1},
        )
    )
    return jsonify(result)


# * AI replies
@app.route("/ai_reply", methods=["POST"])
def ai_reply():
    data = request.get_json()
    user_message = data.get("message", "")

    if not user_message.strip():
        return jsonify({"reply": "Please say something."})

    with gpt_model.chat_session():
        response = gpt_model.generate(user_message, max_tokens=120)

    return jsonify({"reply": response})


# * Private chat history load
@app.route("/private_chat_history/<username>")
def private_chat_history(username):
    if "username" not in session:
        return jsonify([])

    current_user = session["username"]

    chat_history = list(
        messages.find(
            {
                "$or": [
                    {"sender_username": current_user, "recipient": username},
                    {"sender_username": username, "recipient": current_user},
                ],
                "private": True,
            },
            {"_id": 0},
        )
    )

    return jsonify(chat_history)


# * Private chat
@app.route("/private_chat/<username>")
def private_chat(username):
    if "username" not in session:
        return redirect(url_for("login"))

    # ? AI
    if username == "ai_bot":
        return render_template(
            "private_chat.html",
            me=session["fullname"],
            username=session["username"],
            target={"fullname": "ClassBot", "username": "ai_bot"},
            messages=[],
        )

    # ? Users
    target_user = users.find_one({"username": username})
    if not target_user:
        return "User not found."

    current_user = users.find_one({"username": session["username"]})

    # ? Chat history (database)
    chat_history = list(
        messages.find(
            {
                "$or": [
                    {
                        "sender_username": current_user["username"],
                        "recipient": username,
                    },
                    {
                        "sender_username": username,
                        "recipient": current_user["username"],
                    },
                ],
                "private": True,
            },
            {"_id": 0},
        )
    )

    users.update_one(
        {"username": current_user["username"]}, {"$pull": {"unread_chats": username}}
    )

    return render_template(
        "private_chat.html",
        me=current_user["fullname"],
        username=current_user["username"],
        target=target_user,
        messages=chat_history,
    )


#! --> Close Connection to MongoDB <--
@atexit.register
def close_db():
    print("Closing MongoDB connection...")
    client.close()


#! --> Run App <--
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)

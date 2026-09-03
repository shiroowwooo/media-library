import os
import sqlite3
import uuid
import shutil
from pathlib import Path
from datetime import datetime

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    send_from_directory,
    abort,
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "library.db"

IMAGE_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"
}

VIDEO_EXTENSIONS = {
    "mp4", "webm", "mov", "mkv", "avi", "m4v"
}

ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

app = Flask(__name__)

# Maximum request size: 5 GB
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024 * 1024

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database():
    conn = get_db()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            created_at TEXT NOT NULL,

            UNIQUE(name, parent_id),

            FOREIGN KEY(parent_id)
                REFERENCES folders(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            stored_name TEXT NOT NULL UNIQUE,
            original_name TEXT NOT NULL,

            name TEXT NOT NULL,
            extension TEXT NOT NULL,
            media_type TEXT NOT NULL,

            folder_id INTEGER,

            keywords TEXT DEFAULT '',

            size INTEGER DEFAULT 0,

            created_at TEXT NOT NULL,

            FOREIGN KEY(folder_id)
                REFERENCES folders(id)
                ON DELETE SET NULL
        );
    """)

    conn.commit()
    conn.close()


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def clean_name(name):
    name = os.path.basename(str(name)).strip()

    if not name:
        return ""

    return (
        name
        .replace("/", "_")
        .replace("\\", "_")
    )


def get_folder_path(conn, folder_id):
    """
    Converts a database folder ID into its physical
    directory inside uploads/.
    """

    if not folder_id:
        UPLOAD_DIR.mkdir(exist_ok=True)
        return UPLOAD_DIR

    parts = []

    current_id = int(folder_id)

    while current_id:
        row = conn.execute(
            """
            SELECT id, name, parent_id
            FROM folders
            WHERE id = ?
            """,
            (current_id,),
        ).fetchone()

        if not row:
            break

        parts.append(row["name"])
        current_id = row["parent_id"]

    path = UPLOAD_DIR

    for part in reversed(parts):
        path = path / part

    path.mkdir(parents=True, exist_ok=True)

    return path


def build_folder_tree(conn):
    rows = conn.execute(
        """
        SELECT *
        FROM folders
        ORDER BY name COLLATE NOCASE
        """
    ).fetchall()

    children = {}

    for row in rows:
        parent = row["parent_id"]
        children.setdefault(parent, []).append(dict(row))

    def build(parent_id):
        result = []

        for folder in children.get(parent_id, []):
            item = dict(folder)

            item["children"] = build(
                folder["id"]
            )

            result.append(item)

        return result

    return build(None)


def get_file(file_id):
    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM files
        WHERE id = ?
        """,
        (file_id,),
    ).fetchone()

    conn.close()

    return row


# --------------------------------------------------
# MAIN PAGE
# --------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# --------------------------------------------------
# FOLDERS
# --------------------------------------------------

@app.route("/api/folders", methods=["GET"])
def folders():
    conn = get_db()

    tree = build_folder_tree(conn)

    conn.close()

    return jsonify(tree)


@app.route("/api/folders", methods=["POST"])
def create_folder():
    data = request.get_json(silent=True) or {}

    name = clean_name(
        data.get("name", "")
    )

    parent_id = data.get("parent_id")

    if not name:
        return jsonify({
            "error": "Folder name is required"
        }), 400

    conn = get_db()

    try:

        cursor = conn.execute(
            """
            INSERT INTO folders
            (name, parent_id, created_at)
            VALUES (?, ?, ?)
            """,
            (
                name,
                parent_id if parent_id else None,
                datetime.now().isoformat(),
            ),
        )

        conn.commit()

        folder_id = cursor.lastrowid

        get_folder_path(
            conn,
            folder_id
        )

    except sqlite3.IntegrityError:

        conn.close()

        return jsonify({
            "error":
                "A folder with that name already exists here."
        }), 409

    conn.close()

    return jsonify({
        "id": folder_id,
        "name": name,
        "parent_id": parent_id,
    }), 201


@app.route("/api/folders/<int:folder_id>", methods=["DELETE"])
def delete_folder(folder_id):

    conn = get_db()

    folder = conn.execute(
        """
        SELECT *
        FROM folders
        WHERE id = ?
        """,
        (folder_id,),
    ).fetchone()

    if not folder:
        conn.close()

        return jsonify({
            "error": "Folder not found"
        }), 404

    # Files inside the folder are moved to root.
    conn.execute(
        """
        UPDATE files
        SET folder_id = NULL
        WHERE folder_id = ?
        """,
        (folder_id,),
    )

    conn.execute(
        """
        DELETE FROM folders
        WHERE id = ?
        """,
        (folder_id,),
    )

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True
    })


# --------------------------------------------------
# FILE LIST / SEARCH
# --------------------------------------------------

@app.route("/api/files", methods=["GET"])
def list_files():

    search = request.args.get(
        "q",
        ""
    ).strip()

    folder_id = request.args.get(
        "folder_id",
        ""
    )

    conn = get_db()

    sql = """
        SELECT *
        FROM files
        WHERE 1 = 1
    """

    params = []

    if folder_id == "root":

        sql += """
            AND folder_id IS NULL
        """

    elif folder_id:

        sql += """
            AND folder_id = ?
        """

        params.append(
            int(folder_id)
        )

    if search:

        sql += """
            AND (
                name LIKE ?
                OR original_name LIKE ?
                OR keywords LIKE ?
            )
        """

        term = f"%{search}%"

        params.extend([
            term,
            term,
            term,
        ])

    sql += """
        ORDER BY created_at DESC
    """

    rows = conn.execute(
        sql,
        params
    ).fetchall()

    result = []

    for row in rows:

        item = dict(row)

        item["url"] = (
            "/media/" +
            str(row["id"])
        )

        item["download_url"] = (
            "/download/" +
            str(row["id"])
        )

        result.append(item)

    conn.close()

    return jsonify(result)


# --------------------------------------------------
# FILE DETAILS
# --------------------------------------------------

@app.route("/api/files/<int:file_id>", methods=["GET"])
def file_details(file_id):

    conn = get_db()

    row = conn.execute(
        """
        SELECT
            files.*,
            folders.name AS folder_name
        FROM files

        LEFT JOIN folders
            ON files.folder_id = folders.id

        WHERE files.id = ?
        """,
        (file_id,),
    ).fetchone()

    conn.close()

    if not row:
        return jsonify({
            "error": "File not found"
        }), 404

    result = dict(row)

    result["url"] = (
        "/media/" +
        str(file_id)
    )

    result["download_url"] = (
        "/download/" +
        str(file_id)
    )

    return jsonify(result)


# --------------------------------------------------
# UPLOAD
# --------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def upload():

    files = request.files.getlist(
        "files"
    )

    folder_id = (
        request.form.get("folder_id")
        or None
    )

    keywords = (
        request.form.get("keywords")
        or ""
    ).strip()

    if not files:

        return jsonify({
            "error": "No files selected."
        }), 400

    conn = get_db()

    destination = get_folder_path(
        conn,
        folder_id
    )

    created_ids = []

    for uploaded in files:

        if not uploaded.filename:
            continue

        original_name = clean_name(
            uploaded.filename
        )

        extension = (
            Path(original_name)
            .suffix
            .lower()
            .lstrip(".")
        )

        if extension not in ALLOWED_EXTENSIONS:
            continue

        if extension in IMAGE_EXTENSIONS:

            media_type = "image"

        else:

            media_type = "video"

        stored_name = (
            uuid.uuid4().hex +
            Path(original_name).suffix.lower()
        )

        physical_path = (
            destination /
            stored_name
        )

        uploaded.save(
            physical_path
        )

        size = physical_path.stat().st_size

        name = Path(
            original_name
        ).stem

        cursor = conn.execute(
            """
            INSERT INTO files
            (
                stored_name,
                original_name,
                name,
                extension,
                media_type,
                folder_id,
                keywords,
                size,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stored_name,
                original_name,
                name,
                extension,
                media_type,
                folder_id,
                keywords,
                size,
                datetime.now().isoformat(),
            ),
        )

        created_ids.append(
            cursor.lastrowid
        )

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "ids": created_ids,
    })


# --------------------------------------------------
# RENAME / MOVE / TAG
# --------------------------------------------------

@app.route("/api/files/<int:file_id>", methods=["PATCH"])
def update_file(file_id):

    data = request.get_json(
        silent=True
    ) or {}

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM files
        WHERE id = ?
        """,
        (file_id,),
    ).fetchone()

    if not row:

        conn.close()

        return jsonify({
            "error": "File not found"
        }), 404

    new_name = data.get(
        "name",
        row["name"]
    )

    keywords = data.get(
        "keywords",
        row["keywords"]
    )

    new_folder = data.get(
        "folder_id",
        row["folder_id"]
    )

    new_name = clean_name(
        new_name
    )

    if not new_name:

        conn.close()

        return jsonify({
            "error": "Name cannot be empty."
        }), 400

    extension = "." + row["extension"]

    if not new_name.lower().endswith(
        extension.lower()
    ):

        new_name += extension

    old_directory = get_folder_path(
        conn,
        row["folder_id"]
    )

    new_directory = get_folder_path(
        conn,
        new_folder
    )

    old_path = (
        old_directory /
        row["stored_name"]
    )

    new_path = (
        new_directory /
        row["stored_name"]
    )

    # Move physical file.
    if (
        old_path.exists()
        and old_path.resolve()
        != new_path.resolve()
    ):

        shutil.move(
            str(old_path),
            str(new_path)
        )

    conn.execute(
        """
        UPDATE files

        SET
            name = ?,
            original_name = ?,
            keywords = ?,
            folder_id = ?

        WHERE id = ?
        """,
        (
            Path(new_name).stem,
            new_name,
            keywords,
            new_folder,
            file_id,
        ),
    )

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True
    })


# --------------------------------------------------
# DELETE
# --------------------------------------------------

@app.route("/api/files/<int:file_id>", methods=["DELETE"])
def delete_file(file_id):

    conn = get_db()

    row = conn.execute(
        """
        SELECT *
        FROM files
        WHERE id = ?
        """,
        (file_id,),
    ).fetchone()

    if not row:

        conn.close()

        return jsonify({
            "error": "File not found"
        }), 404

    directory = get_folder_path(
        conn,
        row["folder_id"]
    )

    physical_path = (
        directory /
        row["stored_name"]
    )

    if physical_path.exists():

        physical_path.unlink()

    conn.execute(
        """
        DELETE FROM files
        WHERE id = ?
        """,
        (file_id,),
    )

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True
    })


# --------------------------------------------------
# MEDIA PREVIEW
# --------------------------------------------------

@app.route("/media/<int:file_id>")
def media(file_id):

    row = get_file(file_id)

    if not row:
        abort(404)

    conn = get_db()

    directory = get_folder_path(
        conn,
        row["folder_id"]
    )

    conn.close()

    return send_from_directory(
        directory,
        row["stored_name"],
    )


# --------------------------------------------------
# DOWNLOAD
# --------------------------------------------------

@app.route("/download/<int:file_id>")
def download(file_id):

    row = get_file(file_id)

    if not row:
        abort(404)

    conn = get_db()

    directory = get_folder_path(
        conn,
        row["folder_id"]
    )

    conn.close()

    return send_from_directory(
        directory,
        row["stored_name"],
        as_attachment=True,
        download_name=row["original_name"],
    )


# --------------------------------------------------
# ERROR HANDLER
# --------------------------------------------------

@app.errorhandler(413)
def file_too_large(error):

    return jsonify({
        "error":
            "File is too large. Maximum size is 5 GB."
    }), 413


# --------------------------------------------------
# START
# --------------------------------------------------

init_database()

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )

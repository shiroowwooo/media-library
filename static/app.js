let currentFolder = "root";
let currentFolderName = "All Files";
let currentFile = null;
let folderData = [];
let searchTimer = null;


/* --------------------------------------------------
   HELPERS
-------------------------------------------------- */

const $ = id =>
    document.getElementById(id);


async function api(url, options = {}) {

    const response = await fetch(
        url,
        options
    );

    const data =
        await response
            .json()
            .catch(() => ({}));

    if (!response.ok) {

        throw new Error(
            data.error ||
            "Request failed"
        );
    }

    return data;
}


function debounce(
    functionToRun,
    delay = 250
) {

    return (...args) => {

        clearTimeout(
            searchTimer
        );

        searchTimer =
            setTimeout(
                () =>
                    functionToRun(...args),
                delay
            );
    };
}


const debouncedLoad =
    debounce(loadFiles);


/* --------------------------------------------------
   FOLDERS
-------------------------------------------------- */

async function loadFolders() {

    folderData =
        await api(
            "/api/folders"
        );

    const tree =
        $("folderTree");

    tree.innerHTML = "";

    renderFolders(
        folderData,
        tree
    );

    populateFolderSelect();
}


function renderFolders(
    folders,
    parentElement,
    level = 0
) {

    folders.forEach(folder => {

        const wrapper =
            document.createElement(
                "div"
            );

        const button =
            document.createElement(
                "button"
            );

        button.className =
            "folder";

        button.dataset.id =
            folder.id;

        button.style.paddingLeft =
            `${12 + level * 14}px`;

        button.innerHTML =
            `📁 <span>${escapeHtml(
                folder.name
            )}</span>`;

        button.onclick = () =>
            selectFolder(
                String(folder.id),
                folder.name,
                button
            );

        wrapper.appendChild(
            button
        );

        parentElement.appendChild(
            wrapper
        );

        if (
            folder.children &&
            folder.children.length
        ) {

            const child =
                document.createElement(
                    "div"
                );

            child.className =
                "children";

            wrapper.appendChild(
                child
            );

            renderFolders(
                folder.children,
                child,
                level + 1
            );
        }

    });
}


function flattenFolders(
    folders,
    output = []
) {

    folders.forEach(folder => {

        output.push(folder);

        flattenFolders(
            folder.children || [],
            output
        );

    });

    return output;
}


function populateFolderSelect() {

    const select =
        $("detailFolder");

    select.innerHTML =
        `<option value="">
            📁 All Files
        </option>`;

    flattenFolders(
        folderData
    ).forEach(folder => {

        const option =
            document.createElement(
                "option"
            );

        option.value =
            folder.id;

        option.textContent =
            "📁 " + folder.name;

        select.appendChild(
            option
        );

    });
}


/* --------------------------------------------------
   SELECT FOLDER
-------------------------------------------------- */

async function selectFolder(
    id,
    name,
    element
) {

    currentFolder = id;

    currentFolderName =
        name;

    document
        .querySelectorAll(
            ".folder"
        )
        .forEach(button =>
            button.classList.remove(
                "active"
            )
        );

    if (element) {

        element.classList.add(
            "active"
        );
    }

    $("title").textContent =
        name;

    $("breadcrumb").textContent =
        name;

    $("search").value = "";

    await loadFiles();

    if (window.innerWidth <= 760) {

        toggleSidebar(false);
    }
}


/* --------------------------------------------------
   LOAD FILES
-------------------------------------------------- */

async function loadFiles() {

    const query =
        $("search")
            .value
            .trim();

    const url =
        `/api/files?folder_id=${
            encodeURIComponent(
                currentFolder
            )
        }&q=${
            encodeURIComponent(
                query
            )
        }`;

    const files =
        await api(url);

    const grid =
        $("grid");

    grid.innerHTML = "";

    $("count").textContent =
        `${files.length} file${
            files.length === 1
                ? ""
                : "s"
        }`;

    $("empty").hidden =
        files.length !== 0;

    files.forEach(file => {

        grid.appendChild(
            createCard(file)
        );

    });
}


/* --------------------------------------------------
   FILE CARD
-------------------------------------------------- */

function createCard(file) {

    const card =
        document.createElement(
            "div"
        );

    card.className =
        "card";


    const thumb =
        document.createElement(
            "div"
        );

    thumb.className =
        "thumb";


    if (
        file.media_type ===
        "image"
    ) {

        const image =
            document.createElement(
                "img"
            );

        image.src =
            file.url;

        image.loading =
            "lazy";

        image.alt =
            file.name;

        thumb.appendChild(
            image
        );

    } else {

        thumb.innerHTML =
            `
            <div class="file-icon">
                🎥
            </div>

            <div class="play">
                ▶
            </div>
            `;
    }


    const body =
        document.createElement(
            "div"
        );

    body.className =
        "card-body";

    body.innerHTML =
        `
        <div
            class="name"
            title="${escapeAttr(file.name)}"
        >
            ${escapeHtml(file.name)}
        </div>

        <div class="tags">
            ${
                escapeHtml(
                    file.keywords ||
                    "No keywords"
                )
            }
        </div>
        `;


    card.appendChild(
        thumb
    );

    card.appendChild(
        body
    );


    card.onclick = () =>
        openFile(file.id);


    return card;
}


/* --------------------------------------------------
   OPEN FILE
-------------------------------------------------- */

async function openFile(
    fileId
) {

    currentFile =
        await api(
            `/api/files/${fileId}`
        );

    $("detailName").textContent =
        currentFile.name;

    $("detailNameInput").value =
        currentFile.name;

    $("detailKeywords").value =
        currentFile.keywords || "";

    $("detailFolder").value =
        currentFile.folder_id || "";


    const size =
        formatBytes(
            currentFile.size
        );


    $("detailMeta").innerHTML =
        `
        ${currentFile.media_type.toUpperCase()}
        · ${size}

        <br>

        Original:
        ${escapeHtml(
            currentFile.original_name
        )}

        <br>

        Uploaded:
        ${new Date(
            currentFile.created_at
        ).toLocaleString()}
        `;


    $("downloadBtn").href =
        currentFile.download_url;


    if (
        currentFile.media_type ===
        "image"
    ) {

        $("preview").innerHTML =
            `
            <img
                src="${currentFile.url}"
                alt=""
            >
            `;

    } else {

        $("preview").innerHTML =
            `
            <video
                src="${currentFile.url}"
                controls
                autoplay
            ></video>
            `;
    }


    $("modal").hidden =
        false;
}


/* --------------------------------------------------
   CLOSE MODAL
-------------------------------------------------- */

function closeModal() {

    $("modal").hidden =
        true;

    $("preview").innerHTML =
        "";

    currentFile =
        null;
}


/* --------------------------------------------------
   SAVE
-------------------------------------------------- */

async function saveDetails() {

    if (!currentFile) {
        return;
    }

    const name =
        $("detailNameInput")
            .value
            .trim();

    const keywords =
        $("detailKeywords")
            .value
            .trim();

    const folder =
        $("detailFolder")
            .value;


    if (!name) {

        alert(
            "File name cannot be empty."
        );

        return;
    }


    try {

        await api(
            `/api/files/${currentFile.id}`,
            {
                method: "PATCH",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({

                    name: name,

                    keywords:
                        keywords,

                    folder_id:
                        folder ||
                        null
                })
            }
        );


        closeModal();

        await loadFolders();

        await loadFiles();

    } catch (error) {

        alert(
            error.message
        );
    }
}


/* --------------------------------------------------
   DELETE
-------------------------------------------------- */

async function deleteCurrent() {

    if (!currentFile) {
        return;
    }


    const confirmed =
        confirm(
            `Delete "${currentFile.name}"?\n\nThis cannot be undone.`
        );


    if (!confirmed) {
        return;
    }


    try {

        await api(
            `/api/files/${currentFile.id}`,
            {
                method: "DELETE"
            }
        );

        closeModal();

        await loadFiles();

    } catch (error) {

        alert(
            error.message
        );
    }
}


/* --------------------------------------------------
   NEW FOLDER
-------------------------------------------------- */

async function newFolder() {

    const name =
        prompt(
            "New folder name:"
        );


    if (!name || !name.trim()) {
        return;
    }


    const parent =
        currentFolder === "root"
            ? null
            : Number(currentFolder);


    try {

        await api(
            "/api/folders",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({

                    name:
                        name.trim(),

                    parent_id:
                        parent

                })
            }
        );


        await loadFolders();

    } catch (error) {

        alert(
            error.message
        );
    }
}


/* --------------------------------------------------
   UPLOAD
-------------------------------------------------- */

async function uploadFiles(
    fileList
) {

    if (
        !fileList ||
        !fileList.length
    ) {
        return;
    }


    const formData =
        new FormData();


    for (
        const file
        of fileList
    ) {

        formData.append(
            "files",
            file
        );
    }


    if (
        currentFolder !==
        "root"
    ) {

        formData.append(
            "folder_id",
            currentFolder
        );
    }


    const keywords =
        prompt(
            "Optional keywords/tags for these files:",
            ""
        );


    if (
        keywords !== null
    ) {

        formData.append(
            "keywords",
            keywords
        );
    }


    try {

        await api(
            "/api/upload",
            {
                method: "POST",
                body: formData
            }
        );

        await loadFiles();

    } catch (error) {

        alert(
            error.message
        );
    }
}


/* --------------------------------------------------
   FILE INPUT
-------------------------------------------------- */

$("fileInput")
    .addEventListener(
        "change",
        event => {

            uploadFiles(
                event.target.files
            );

            event.target.value =
                "";
        }
    );


/* --------------------------------------------------
   DRAG AND DROP
-------------------------------------------------- */

const dropZone =
    $("dropZone");


[
    "dragenter",
    "dragover"
].forEach(eventName => {

    dropZone.addEventListener(
        eventName,
        event => {

            event.preventDefault();

            dropZone.style.borderColor =
                "#5b5cf0";
        }
    );

});


[
    "dragleave",
    "drop"
].forEach(eventName => {

    dropZone.addEventListener(
        eventName,
        event => {

            event.preventDefault();

            dropZone.style.borderColor =
                "";
        }
    );

});


dropZone.addEventListener(
    "drop",
    event => {

        uploadFiles(
            event.dataTransfer.files
        );

    }
);


dropZone.addEventListener(
    "click",
    () =>
        $("fileInput").click()
);


/* --------------------------------------------------
   MOBILE SIDEBAR
-------------------------------------------------- */

function toggleSidebar(
    force
) {

    const sidebar =
        $("sidebar");

    if (force === false) {

        sidebar.classList.remove(
            "open"
        );

    } else {

        sidebar.classList.toggle(
            "open"
        );
    }
}


/* --------------------------------------------------
   FORMATTING
-------------------------------------------------- */

function formatBytes(
    bytes
) {

    if (!bytes) {
        return "0 B";
    }

    const units = [
        "B",
        "KB",
        "MB",
        "GB",
        "TB"
    ];

    let index = 0;

    let value = bytes;


    while (
        value >= 1024 &&
        index <
            units.length - 1
    ) {

        value /= 1024;

        index++;
    }


    return `${
        value.toFixed(
            index === 0
                ? 0
                : 1
        )
    } ${units[index]}`;
}


/* --------------------------------------------------
   SECURITY
-------------------------------------------------- */

function escapeHtml(
    value
) {

    return String(value)
        .replace(
            /[&<>"']/g,
            character => {

                const map = {

                    "&": "&amp;",
                    "<": "&lt;",
                    ">": "&gt;",
                    '"': "&quot;",
                    "'": "&#039;"
                };

                return map[
                    character
                ];
            }
        );
}


function escapeAttr(
    value
) {

    return escapeHtml(value);
}


/* --------------------------------------------------
   INITIAL LOAD
-------------------------------------------------- */

async function initialize() {

    try {

        await loadFolders();

        await loadFiles();

    } catch (error) {

        alert(
            error.message
        );
    }
}


initialize();

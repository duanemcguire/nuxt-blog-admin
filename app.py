# ------------------------------------------------------
# Web app to update a nuxt blog repository on Github.
# The app is compatable with the blog, git@github.com:duanemcguire/duaneblog.git
#   and others that I have put together with nuxt.
# By linking the repository to a netlify deploy this app opens
#   admin to the non-techie and the lazy techie.
# ------------------------------------------------------

from flask import Flask, flash, render_template, request
from flask_uploads import IMAGES, UploadSet, configure_uploads
from datetime import datetime
import urllib.request
import os, glob, base64
from os.path import exists
from os import environ
import logging
import sys
import json
import markdown
from datetime import date, datetime
from github import Github
from PIL import Image
import shortuuid
from inflection import parameterize
import time

app = Flask(__name__)

# -------------Configuration-------------------------
# github api token saved as environment variable
gToken = environ.get("GTOKEN")

# repository name saved as environment variable
repository = environ.get("REPO")

# dir references the content directory of blog posts
# for duaneblog, that is "content/blog"
blog = {
    "dir": environ.get("BLOG_CONTENT_DIR"),
    "imagepath": environ.get("BLOG_IMAGE_PATH"),
}

misc_content = {
    "dir": environ.get("BLOG_REPO_MISC_CONTENT_DIR"),
    "repo_image_path": environ.get("REPO_BLOG_IMAGE_PATH"),
    "web_image_path": environ.get("BLOG_WEB_IMAGE_PATH")
}

# markdown meta keys available by default
# e.g. title, date, category, tags
default_meta_keys = environ.get("DEFAULT_META_KEYS")

g = Github(gToken)
# location of local photo directory to temporarily stash images
# while editing a post
photodest = "static/img"

# Used by PIL image manager
app.config["SECRET_KEY"] = os.urandom(24)
app.config["UPLOADED_PHOTOS_DEST"] = app.root_path + "/" + photodest
photodestfull = app.config["UPLOADED_PHOTOS_DEST"]
photos = UploadSet("photos", IMAGES)
configure_uploads(app, photos)
# ----------End Configuration-------------------------


def process_new_photo(upImage, upCaption, path, photoset, makeThumb=False):
    # Handle uploaded photo
    filename = photos.save(upImage)
    image = Image.open(f"{photodestfull}/{filename}")
    ratio = image.size[0] / image.size[1]
    w = 800
    h = int(w / ratio)
    resized = image.resize((w, h))
    filename = shortuuid.uuid() + "." + filename.split(".")[-1]

    # save to local file stash
    resized.save(f"{photodestfull}/{filename}")
    photoInstance = {}
    photoInstance["path"] = f"{blog['imagepath']}/{filename}"
    photoInstance["caption"] = upCaption

    # save new photo to github
    f = open(f"{photodestfull}/{filename}", "rb")
    thispic = f.read()
    repo = g.get_repo(repository)
    repo.create_file(f"static{photoInstance['path']}", "app", thispic, branch="main")
    if makeThumb:
        create_thumbnail(filename)
        photoInstance["thumbnail"] = "True"
    else:
        photoInstance["thumbnail"] = "False"
    photoset.append(photoInstance)
    return photoset


def create_thumbnail(filename):
    # create a 320px wide thumbnail for display in blog_card in listing of posts
    filename = filename.split("/").pop()
    repo = g.get_repo(repository)
    newThumb = True
    try:
        contents = repo.get_contents(
            f"static{blog['imagepath']}/thumb/{filename}", ref="main"
        )
        if contents:
            # the thumbnail is already present.
            newThumb = False
    except Exception as err:
        pass

    if newThumb:
        # one thumbnail per blog post.  Delete all from local thumb dir
        # delete matching names from repo
        filelist = glob.glob(f"{photodestfull}/thumb/*")
        for filepath in filelist:
            os.remove(filepath)
            fn = filepath.split("/").pop
            try:
                contents = repo.get_contents(
                    f"static{blog['imagepath']}/thumb/{fn}", ref="main"
                )
                repo.delete_file(contents.path, "app", contents.sha, branch="main")
            except Exception as err:
                flash(f"Error while deleting unneeded thumbnail: {err}")

        # resize the image
        image = Image.open(f"{photodestfull}/{filename}")
        ratio = image.size[0] / image.size[1]
        w = 320
        h = int(w / ratio)
        resized = image.resize((w, h))
        if h > 240:
            left = 0
            right = 320
            top = 0
            bottom = 240
            newimg = resized.crop((left, top, right, bottom))
            newsize = (320, 240)
            resized = newimg.resize(newsize)
        resized.save(f"{photodestfull}/thumb/{filename}")

        # save the thumbnail in the repository
        f = open(f"{photodestfull}/thumb/{filename}", "rb")
        thispic = f.read()
        try:
            repo.create_file(
                f"static{blog['imagepath']}/thumb/{filename}",
                "app",
                thispic,
                branch="main",
            )
        except:
            None

    return True


def init_working_dir(path):
    # photo directory is established for the current markdown file
    # files are wiped when we begin editing a different markdown file

    # path.txt contains the path of the current post's markdown file
    path_text_file = f"{photodestfull}/path.txt"
    last_path = ""
    if exists(path_text_file):
        f = open(path_text_file, "r")
        last_path = f.read()
    if path != last_path:
        # Last used for a different path
        # Re-initialize the directory

        # remove the existing images
        filelist = glob.glob(photodestfull + "/*")
        for filepath in filelist:
            if not os.path.isdir(filepath):
                os.remove(filepath)

        # write the new path to path.txt
        f = open(path_text_file, "w")
        f.write(path)
        f.close()

        # remove the existing thumbnail(s)
        thumbpath = f"{photodestfull}/thumb"
        filelist = glob.glob(thumbpath + "/*")
        for filepath in filelist:
            os.remove(filepath)

    return True


def github_save_file(path):
    # Save photo from repository to photo directory

    filename = path.split("/")[-1]
    photo_path = f"{photodestfull}/{filename}"
    if not exists(photo_path):
        try:
            g = Github(gToken)
            g_path = f"static{path}"
            repo = g.get_repo(repository)
            content_encoded = repo.get_contents(
                urllib.parse.quote(g_path), ref="main"
            ).content
            content = base64.b64decode(content_encoded)
            filename = path.split("/")[-1]
            f = open(f"{photodestfull}/{filename}", "wb")
            f.write(content)
            f.close()
        except:
            flash(f"{g_path} is missing ")
    return True


def delete_images(deleteList):
    # delete images from repository
    # images need not be deleted locally.  Local images are temporary anyway.
    repo = g.get_repo(repository)

    for img in deleteList:
        # delete listed Image
        try:
            contents = repo.get_contents(f"static{img}", ref="main")
            repo.delete_file(contents.path, "app", contents.sha, branch="main")
        except:
            None
        # delete possible thumbnail of the same name
        pathList = img.split("/")
        fn = pathList.pop()
        pathOnly = "/".join(pathList)
        thumbPath = pathOnly + "/" + "thumb" + "/" + fn
        try:
            contents = repo.get_contents(f"static{thumbPath}", ref="main")
            repo.delete_file(contents.path, "app", contents.sha, branch="main")
        except:
            None
    return True


def load_working_dir(photoset):
    # save photos from github to the local working directory  (photodest)
    for p in photoset:
        #        print(p)
        github_save_file(p["path"])
    return True


def build_path(title):
    # create path for blog post from blog title
    path = f"{blog['dir']}/{parameterize(title)}.md"
    init_working_dir(path)
    return path


############################################################################
@app.route("/")
def get_repo():
    # get a list of posts (markdown files) from the repository
    # display in the root.html template

    files = []
    repo = g.get_repo(repository)
    # print(repo.name)
    contents = repo.get_contents(blog["dir"])
    for content_file in contents:
        files.append(content_file.path)
    ldir = blog["dir"] + "/"

    return render_template("root.html", **locals())

@app.route("/pages")
def get_pages():
    # get a list of main page content (markdown files) from the repository
    # display in the root.html template

    files = []
    repo = g.get_repo(repository)
    # print(repo.name)
    contents = repo.get_contents(blog["dir"])
    for content_file in contents:
        files.append(content_file.path)
    ldir = blog["dir"] + "/"

    return render_template("root.html", **locals())

@app.route("/edit")
def edit_file(path=""):
    # read the specified markdown file
    # display filecontent and meta data for editing in edit-file.html

    repo = g.get_repo(repository)
    if path == "":
        path = request.args.get("f")
    init_working_dir(path)
    ldir = blog["dir"] + "/"
    filename = path.split(ldir)[1].split(".md")[0]
    file = repo.get_contents(path)
    file_content = file.decoded_content.decode()
    fcsplit = file_content.split("---")
    filetext = fcsplit[len(fcsplit) - 1].strip()
    md = markdown.Markdown(extensions=["meta"])
    html = md.convert(file_content)
    for k, v in md.Meta.items():
        if k == "photoset":
            photoset = json.loads(v[0])
            load_working_dir(photoset)

    return render_template("edit-file.html", **locals())


@app.route("/add")
def add_file():
    # prepare default data
    # display in add-file.html for creation of new post

    ldir = blog["dir"] + "/"
    meta_keys = default_meta_keys
    thisDay = datetime.today().strftime("%Y-%m-%d")
    return render_template("add-file.html", **locals())


@app.route("/post-new", methods=["POST"])
def post_new_file():
    # read form data from add-file.html
    # create local images
    # save images and markdown file to the repository

    repo = g.get_repo(repository)
    filecontent = request.form["filecontent"]
    photoset = []
    photocount = 0
    path = ""

    # initialize filecontent of new post with markdown meta data separator
    fc = "---\n"

    for k, v in request.form.items():
        # build meta data string
        if (
            k != "filecontent"
            and k.find("photo_") == -1
            and k != "path"
            and k.find("__") == -1
        ):
            if ((" " in v) or (k == "date")) and v[0] != "[":
                v = '"' + v + '"'
            fc = fc + k + ": " + v + "\n"
            if k == "title":
                path = build_path(v)
                file = path
    # auto-supply an ID greater than all others.
    id = str(int(time.time()))
    fc = fc + "id" + ": " + id + "\n"

    if request.files["__new_photo"].filename > "":
        photo = request.files["__new_photo"]
        caption = request.form["__new_photo__caption"]
        makeThumb = True

        # process the new photo which will save a full size and thumbnail to the repository
        photoset = process_new_photo(photo, caption, file, photoset, makeThumb)

    p = json.dumps(photoset)

    # append the photoset and filecontent to complete the markdown file
    fc = fc + "photoset: " + p + "\n"
    fc = fc + "---\n"
    fc = fc + filecontent

    # save the markdown file to the repository.
    repo.create_file(path, "app", fc, branch="main")
    flash(path + " created")
    return edit_file(path)


@app.route("/post-file", methods=["POST"])
def post_file():
    # read form data from edit-file.html
    # create local images
    # save images and update the markdown file in the repository

    repo = g.get_repo(repository)
    path = request.form["path"]
    file = repo.get_contents(path)
    filecontent = request.form["filecontent"]
    photoset = []
    photocount = 0

    # initialize the filecontent with the markdown metadata separator
    fc = "---\n"

    # build the metadata string for the markdown file
    for k, v in request.form.items():
        if k != "filecontent" and k.find("myphoto") == -1 and k.find("__") == -1:
            if ((" " in v) or (k == "date")) and v[0] != "[":
                v = '"' + v + '"'
            fc = fc + k + ": " + v + "\n"
    #
    pathList = request.form.getlist("myphoto_path")
    captionList = request.form.getlist("myphoto_caption")
    deleteList = request.form.getlist("myphoto_delete")

    # delete any images marked for deletion in the form
    delete_images(deleteList)

    # build the revised photoset
    # separate indexes i and j reflect that images may have been deleted
    #   by user de-selection in the form
    i = -1
    j = -1
    for p in pathList:
        j = j + 1
        if p not in deleteList:
            i = i + 1
            photoset.append({})
            photoset[i]["path"] = p
            photoset[i]["caption"] = captionList[j]
            if request.form["myphoto_thumbnail"] == p:
                photoset[i]["thumbnail"] = "True"
                create_thumbnail(p)

    # process any new photo
    if request.files["__new_photo"].filename > "":
        photoset = process_new_photo(
            request.files["__new_photo"],
            request.form["__new_photo__caption"],
            file,
            photoset,
        )
    p = json.dumps(photoset)
    fc = fc + "photoset: " + p + "\n"
    fc = fc + "---\n"
    fc = fc + filecontent

    # update the markdown file in the repository
    repo.update_file(path, "saved by app", fc, file.sha)
    flash(path + " repo updated")
    return edit_file(path)


@app.route("/delete")
def delete_file(path=""):
    # delete a post (markdown file and associated images) from the repository
    repo = g.get_repo(repository)
    path = request.args.get("f")
    file = repo.get_contents(path)
    file_content = file.decoded_content.decode()
    md = markdown.Markdown(extensions=["meta"])
    html = md.convert(file_content)
    photoset = []
    for k, v in md.Meta.items():
        if k == "photoset":
            photoset = json.loads(v[0])
    if len(photoset) > 0:

        # delete the images
        for photodef in photoset:
            try:
                repoPath = f"static{photodef['path']}"
                file = repo.get_contents(repoPath)
                contents = repo.get_contents(repoPath, ref="main")
                repo.delete_file(contents.path, "app", contents.sha, branch="main")
                if "thumbnail" in photodef.keys():
                    if photodef["thumbnail"] == "True":
                        fn = photodef["path"].split("/").pop()
                        repoPath = f"static{blog['imagepath']}/thumb/{fn}"
                        contents = repo.get_contents(repoPath, ref="main")
                        repo.delete_file(
                            contents.path, "app", contents.sha, branch="main"
                        )
            except Exception as err:
                flash(f"Error deleting photoset: {err}")
    try:

        # delete the markdown file
        path = request.args.get("f")
        contents = repo.get_contents(path, ref="main")
        repo.delete_file(contents.path, "app", contents.sha, branch="main")
    except Exception as err:
        flash(f"Error deleting post: {err}")
    else:
        flash(f"Deleted {path}")

    # display main page
    return get_repo()

#!/usr/bin/env python
import os
import re
import os.path
import sys
import shutil
import collections
import glob
import json
import subprocess
import tempfile
import string

import xml.etree.ElementTree as ET
try:
    import yaml
except ImportError:
    print >> sys.stderr, "You need to install pyyaml using pip or easy_install, sorry"
    sys.exit(-10)

Theme = collections.namedtuple('Theme','id name language stylesheets legal logo css_variables')
Style = collections.namedtuple('Style', 'name template stylesheets')
Language = collections.namedtuple('Language', 'code name legal translations')

def translate(self, text):
    return self.translations.get(text, text)

Language.translate=translate

base = os.path.dirname(os.path.abspath(__file__))
template_base = os.path.join(base, "templates")

with open(os.path.join(template_base, "uk_legal.html")) as fh:
    uk_legal = fh.read()

with open(os.path.join(template_base, "world_legal.html")) as fh:
    world_legal = fh.read()

note_style = index_style = Style(
    name = 'lesson', 
    template = "template.html",
    stylesheets = ["/css/main.css", "/css/notes.css"],
)
index_style = Style(
    name = 'lesson', 
    template = "template.html",
    stylesheets = ["/css/main.css", "/css/index.css"],
)
lesson_style = Style(
    name = 'lesson', 
    template = "template.html",
    stylesheets = ["/css/main.css","/css/lesson.css"],
)

codeclubworld = Theme(
    id='world',
    language='en-GB',
    name='Code Club World',
    legal = world_legal,
    stylesheets = [],
    logo = "/img/ccw_logo.svg",
    css_variables = {
        "header_bg_light": "#ADCAEA",
        "header_bg_dark": "#007CC9",
        "header_text": "#FFFFFF",
    }
)

codeclubuk = Theme(
    id='uk',
    language='en-GB',
    name='Code Club',
    legal = uk_legal,
    stylesheets = [],
    logo = "/img/ccuk_logo.svg",
    css_variables = {
        "header_bg_light": "#B1DAAE",
        "header_bg_dark": "#349946",
        "header_text": "#FFFFFF",
    }
)

EN_GB=Language(code='en-GB', name='English', legal={}, translations={})
LANGUAGES = {
 'en-GB' : EN_GB,
}

# todo : real classes

Term = collections.namedtuple('Term', 'id title description language number projects extras')
Project = collections.namedtuple('Project', 'filename number title materials note embeds')
Extra = collections.namedtuple('Extra', 'name materials note')
Resource = collections.namedtuple('Resource','format filename')

css_assets = os.path.join(template_base,"css")

scratchblocks_filter = os.path.join(base, "pandoc_scratchblocks/filter.py")
html_assets = [os.path.join(base, "assets",x) for x in ("fonts", "img")]

# Markup processing

def pandoc_html(input_file, style, language, theme, variables, commands, output_file):
    legal = language.legal.get(theme.id, theme.legal)

    cmd = [
        "pandoc",
        input_file, 
        "-o", output_file,
        "-t", "html5",
        "-s",  # smart quotes
        "--highlight-style", "pygments",
        "--section-divs",
        "--template=%s"%os.path.join(template_base, style.template), 
        "--filter", scratchblocks_filter,
        "-M", "legal=%s"%legal,
        "-M", "theme=%s"%theme.name,
        "-M", "logo=%s"%theme.logo,
    ]
    for stylesheet in style.stylesheets:
        cmd.extend(("-c", stylesheet,))
    for stylesheet in theme.stylesheets:
        cmd.extend(("-c", stylesheet,))
    for k,v in variables.iteritems(): 
        cmd.extend(("-M", "%s=%s"%(k,v)))
    
    working_dir = os.path.dirname(output_file)

    subprocess.check_call(cmd, cwd=working_dir)


    
def build_pdf(markdown_file, style, output_file):
    # todo: add pandoc call, but use a different template
    # than the default, or perhaps a lua writer for xetex.
    # then call xetex :/
    pass

def markdown_to_html(markdown_file, style, language, theme, output_file):
    commands = (
        "-f", "markdown_github+header_attributes+yaml_metadata_block+inline_code_attributes",
    )

    pandoc_html(markdown_file, style, language, theme, {}, commands, output_file)

def make_html(variables, html, style, language, theme, output_file):
    variables = dict(variables)
    variables['body'] = ET.tostring(html, encoding='utf-8', method='html')

    commands = (
        "-f", "html",
        "-R",
    )
    
    input_file = '/dev/null'

    pandoc_html(input_file, style, language, theme, variables, commands, output_file)


def process_file(input_file, style, language, theme, output_dir):
    output = []
    name, ext = os.path.basename(input_file).rsplit(".",1)
    if ext == "md":
        output_file = os.path.join(output_dir, "%s.html"%name)
        markdown_to_html(input_file, style, language, theme, output_file)
        output.append(Resource(filename=output_file, format="html"))
    else:
        output_file = os.path.join(output_dir, os.path.basename(input_file))
        shutil.copy(input_file, output_file)
        output.append(Resource(filename=output_file, format=ext))
    return output 

# Process files within project and resource containers

def build_project(term, project, language, theme, output_dir):
    # todo clean up this code because we keep repeating things.

    input_file = project.filename
    name, ext = os.path.basename(input_file).rsplit(".",1)

    output_files = process_file(input_file, lesson_style, language, theme, output_dir)

    notes = []

    if project.note:
        notes.extend(process_file(project.note, note_style, language, theme, output_dir))
    
    materials = None
    if project.materials:
        zipfilename = "%s_%d-%02.d_%s_%s.zip" % (term.id, term.number, project.number, project.name, language.translate("resources"))
        materials = zip_files(project.materials,output_dir, zipfilename)

    embeds = []
    for file in project.embeds:
        embeds.append(copy_file(file, output_dir))

    return Project(
        filename = output_files,
        number = project.number,
        title = project.title,
        materials = materials,
        note = notes,
        embeds = embeds,
    )


def build_extra(term, extra, language, theme, output_dir):
    note = []
    if extra.note:
        note.extend(process_file(extra.note, note_style, language, theme, output_dir))
    materials = None
    if extra.materials:
        zipfilename = "%s_%d_%s_%s.zip" % (term.id, term.number, extra.name, language.translate("resources"))
        materials = zip_files(extra.materials,output_dir, zipfilename)
    return Extra(name = extra.name, note=note, materials=materials)

# Building indexes

def sort_files(files):
    sort_key = {
        'html':2,
        'pdf':1,
    }
    return sorted(files, key=lambda x:sort_key.get(x.format,0), reverse=True)

def make_term_index(term, language, theme, output_dir):

    output_file = os.path.join(output_dir, "index.html")
    title = term.title

    root = ET.Element('body')
    if term.description:
        section = ET.SubElement(root,'section', {'class':'description'})
        p = ET.SubElement(section, 'p')
        p.text = term.description

    section = ET.SubElement(root,'section', {'class':'projects'})
    h1 = ET.SubElement(section,'h1')
    h1.text = language.translate("Projects")
    ol = ET.SubElement(root, 'ol', {'class': 'projectlist'})
    
    for project in sorted(term.projects, key=lambda x:x.number):
        li = ET.SubElement(ol, 'li')
        ul = ET.SubElement(li, 'ul', {'class': 'projectfiles'})

        files = sort_files(project.filename)
        first, others = files[0], files[1:]

        url = os.path.relpath(first.filename, output_dir)

        a_li = ET.SubElement(ul, 'li')
        a = ET.SubElement(a_li, 'a', {'href': url, 'class':'worksheet'})
        a.text = project.title or url

        for file in others:
            url = os.path.relpath(file.filename, output_dir)
            a_li = ET.SubElement(ul, 'li')
            a = ET.SubElement(a_li, 'a', {'href': url, 'class':'alternate'})
            a.text = file.format
            
        for file in sort_files(project.note):
            url = os.path.relpath(file.filename, output_dir)
            a_li = ET.SubElement(ul, 'li')
            a = ET.SubElement(a_li, 'a', {'href': url, 'class':'notes'})
            if file.format != 'html':
                a.text = "%s (%s)"%(language.translate("Notes"),file.format)
            else:
                a.text = language.translate("Notes")


    section = ET.SubElement(root, 'section', {'class':'extras'})
    h1 = ET.SubElement(section, 'h1')
    h1.text = language.translate('Extras')

    ol = ET.SubElement(root, 'ol', {'class':'extralist'})
    for extra in term.extras:
        if extra.note:
            file = sort_files(extra.note)[0]
            # todo: handle multiple formats
            url = os.path.relpath(file.filename, output_dir)
            li = ET.SubElement(ol, 'li', {'class':'extranote'})
            a = ET.SubElement(li, 'a', {'href': url})
            a.text = extra.name
        
        
        if extra.materials: 
            filename = extra.materials
            url = os.path.relpath(filename, output_dir)
            li = ET.SubElement(ol, 'li', {'class':'extramaterial'})
            a = ET.SubElement(li, 'a', {'href': url})
            a.text = filename


    make_html({'title':title, 'level':"T%d"%term.number}, root, index_style, language, theme, output_file)
    return output_file, term


def make_lang_index(language, terms, theme, output_dir):
    output_file = os.path.join(output_dir, "index.html")

    root = ET.Element('section', {'class':'termlist'})
    h1 = ET.SubElement(root, 'h1')
    h1.text = language.translate("Terms")
    ol = ET.SubElement(root, 'ol')
    for term_index, term in sorted(terms, key=lambda x:x[1].number):
        url = os.path.relpath(term_index, output_dir)

        li = ET.SubElement(ol, 'li', {'class':'term'})
        a = ET.SubElement(li, 'a', {'href': url})
        a.text = term.title or url


    make_html({'title':language.name}, root, index_style, language, theme, output_file)
    return output_file

def make_index(languages, language, theme, output_dir):
    output_file = os.path.join(output_dir, "index.html")
    title = theme.name

    root = ET.Element('section')
    h1 = ET.SubElement(root, 'h1')
    h1.text = language.translate("Languages")
    ol = ET.SubElement(root, 'ol', {'class':'langs'})

    for lang, filename in languages:
        url = os.path.relpath(filename, output_dir)

        li = ET.SubElement(ol, 'li', {'class':'lang'})
        a = ET.SubElement(li, 'a', {'href': url})
        a.text = lang.name


    make_html({'title':title}, root, index_style, language, theme, output_file)

# The all singing all dancing build function of doing everything.

def build(repositories, theme, output_dir):

    print "Searching for manifests .."

    termlangs = {}
    
    for m in find_files(repositories, ".manifest"):
        print "Found Manifest:", m
        try:
            term = parse_manifest(m)
            if term.language not in termlangs:
                termlangs[term.language] = []
            termlangs[term.language].append(term)
        except StandardError as e:

            import traceback
            traceback.print_exc()
            print "Failed", e

    print "Copying assets"

    copydir(html_assets, output_dir)
    css_dir = os.path.join(output_dir, "css")
    makedirs(css_dir)
    make_css(css_assets, theme, css_dir)

    languages = {}
    project_count = {}

    for language_code, terms in termlangs.iteritems():
        if language_code not in LANGUAGES:
            LANGUAGES[language_code] = Language(
                code = language_code,
                name = language_code,
                legal = {},
                translations = {}
            )
        language = LANGUAGES[language_code]
        print "Language", language.name
        out_terms = []
        count = 0;
        lang_dir = os.path.join(output_dir, language.code)

        for term in terms:
            term_dir = os.path.join(lang_dir, "%s.%d"%(term.id, term.number))
            makedirs(term_dir)
            
            print "Building Term:", term.title,

            projects = []
            
            for p in term.projects:
                count+=1
                project = parse_project_meta(p)
                print "Building Project:", project.title, project.filename

                project_dir = os.path.join(term_dir,"%.02d"%(project.number))
                makedirs(project_dir)

                built_project = build_project(term, project, language, theme, project_dir)
                
                projects.append(built_project)

            extras = []
            
            for r in term.extras:
                print "Building Extra:", r.name
                extras.append(build_extra(term, r, language, theme, term_dir))

            term = Term(
                id = term.id,
                number = term.number, language = term.language,
                title = term.title, description= term.description,
                projects = projects,
                extras = extras,
            )

            out_terms.append(make_term_index(term, language, theme, term_dir))

            print "Term built!"

        print "Building",language.name,"index"

        languages[language_code]=make_lang_index(language, out_terms, theme, lang_dir)
        project_count[language_code]=count

    print "Building", theme.name, "index"

    sorted_languages =  []
    for lang in sorted(project_count.keys(), key=lambda x:project_count[x], reverse=True):
        sorted_languages.append((LANGUAGES[lang], languages[lang]))


    make_index(sorted_languages,LANGUAGES[theme.language], theme, output_dir)
    print "Complete"
    
# Manifest and Project Header Parsing

def parse_manifest(filename):
    with open(filename) as fh:
        json_manifest = json.load(fh)
    
    base_dir = os.path.join(os.path.dirname(filename))

    projects = []
    for p in json_manifest['projects']:
        filename = expand_glob(base_dir, p['filename'], one_file=True)
        materials = expand_glob(base_dir, p.get('materials',[]))
        embeds = expand_glob(base_dir, p.get('embeds',[]))

        if 'note' in p:
            note = expand_glob(base_dir, p['note'], one_file=True)
        else:
            note = None
    
        project = Project(
            filename = filename,
            number = p['number'],
            title = p.get('title', None),
            materials = materials,
            note = note,
            embeds = embeds,
        )
        projects.append(project)

    extras = []
    for s in json_manifest.get('extras',()):
        if 'note' in s:
            note = expand_glob(base_dir, s['note'], one_file=True)
        else:
            note = None
        materials = expand_glob(base_dir, s.get('materials', ()))
        
        extras.append(Extra(
            name=s['name'],
            note=note,
            materials=materials,
        ))

    m = Term(
        id = json_manifest['id'],
        title = json_manifest['title'],
        description = json_manifest['description'],
        language = json_manifest['language'],
        number = int(json_manifest['number']),
        projects = projects,
        extras = extras,
    )

    return m

def parse_project_meta(p):
    if not p.filename.endswith('md'):
        return p

    with open(p.filename) as fh:

        in_header = False
        header_lines = []
        for line in fh.readlines():
            l = line.strip()
            if l == "---":
                in_header = True
            elif l == "...":
                in_header = False
            elif in_header:
                header_lines.append(line)
    header = yaml.safe_load("".join(header_lines))

    if header:
        title = header.get('title', p.title)
        number = header.get('number', p.number)
        title = header.get('title', p.title)

        raw_note = header.get('note', None)
        if raw_note:
            base_dir = os.path.dirname(p.filename)
            note = expand_glob(base_dir, raw_note, one_file=True)
        else:
            note = p.note

        raw_materials = header.get('materials', ())
        if raw_materials:
            base_dir = os.path.dirname(p.filename)
            materials = expand_glob(base_dir, raw_materials)
            materials.extend(p.materials)
        else:
            materials = p.materials

        raw_embeds = header.get('embeds', ())
        if raw_embeds:
            base_dir = os.path.dirname(p.filename)
            embeds = expand_glob(base_dir, raw_embeds)
            embeds.extend(p.embeds)
        else:
            embeds = p.embeds

        return Project(
            filename = p.filename,
            number = number,
            title = title,
            materials = materials,
            note = note,
            embeds = embeds,
        )
    else:
        return p

def make_css(stylesheet_dir, theme, output_dir):
    for asset in os.listdir(stylesheet_dir):
        if not asset.startswith('.'):
            src = os.path.join(stylesheet_dir, asset)
            dst = os.path.join(output_dir, asset)
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                    makedirs(dst)
                else:
                    os.remove(dst)
                    
            if os.path.isdir(src):
                make_css(src, theme, dst)
            else:
                if asset.endswith('.css'):
                    with open(src,"r") as src_fh, open(dst,"w") as dst_fh:
                        template = string.Template(src_fh.read())
                        dst_fh.write(template.substitute(theme.css_variables))

                else:
                    shutil.copy(src, output_dir)
    
# File and directory handling

def find_files(dir, extension):
    manifests = []
    def visit(m, dirname, names):
        for n in names:
            if n.endswith(extension):
                m.append(os.path.join(dirname, n))
    for d in dir:
        os.path.walk(d, visit, manifests)
    
        
    return manifests

def expand_glob(base_dir, paths, one_file=False):
    if one_file:
        output = glob.glob(os.path.join(base_dir, paths))
        if len(output) != 1:
            raise AssertionError("Bad things")
        return output[0]

    else:
        output = []
        if not hasattr(paths, '__iter__'):
            paths = (paths,)
        for p in paths:
            output.extend(glob.glob(os.path.join(base_dir, p)))
        return output
    
def makedirs(path, clear=False):
    if clear and os.path.exists(path):
        shutil.rmtree(path)
    if not os.path.exists(path):
        os.makedirs(path)

banned_chars= re.compile(r'[\\/?|;:!#@$%^&*<>, ]')
def safe_filename(filename):
    return banned_chars.sub(filename, "_")

def zip_files(source_files, output_dir, output_file):
    if source_files:
        output_file = os.path.join(output_dir, safe_filename(output_file))
        cmd = [
            'zip', '-f', output_file,
        ]
        for file in source_files:
            cmd.append(safe_filename(source_files))

        subprocess.check_call(zip_files)
        return output_file
    else:
        return None


def copydir(assets, output_dir):
    for src in assets:
        asset = os.path.basename(src)
        if not asset.startswith('.'):
            dst = os.path.join(output_dir, asset)
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
                    
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy(src, output_dir)


def copy_file(input_file, output_dir):
        name, ext = os.path.basename(input_file).rsplit(".",1)
        output_file = os.path.join(output_dir, os.path.basename(input_file))
        shutil.copy(input_file, output_file)
        return output_file


if __name__ == '__main__':
    args = sys.argv[1::]
    if len(args) < 3:
        print "usage: %s <region> <input repository directories> <output directory>"
        sys.exit(-1)

    theme = {'world':codeclubworld, 'uk':codeclubuk}[args[0]]
    args = [os.path.abspath(a) for a in args[1:]]

    repositories, output_dir = args[:-1], args[-1]

    build(repositories, theme, output_dir)

    sys.exit(0)


import io
import gc
import time
import json
from aiohttp import web
from bson.objectid import ObjectId
from utils import temp, get_size
from info import BIN_CHANNEL, MAX_WEB_RESULTS
from database.ia_filterdb import actors, get_search_results
from web.web_assets import build_page, get_auth, form_wrapper

actor_routes = web.RouteTableDef()

# ─────────────────────────────────────────────────────────
# 🎭 PUBLIC VIEW: ACTORS DIRECTORY CATALOG PAGE
# ─────────────────────────────────────────────────────────
@actor_routes.get('/actors')
async def actors_directory_page(req):
    role, _ = await get_auth(req)
    if not role: return web.HTTPFound('/login')
        
    cursor = actors.find({}).sort("created_at", -1)
    all_actors = await cursor.to_list(length=200)
    
    admin_header_action = ""
    if role == 'admin':
        admin_header_action = '''
        <div style="display:flex; justify-content:flex-end; margin-bottom:25px;">
            <a href="/admin/create_actor" style="background:var(--accent); color:#fff; padding:12px 24px; border-radius:8px; font-weight:700; text-decoration:none; font-size:14px; transition:0.2s; box-shadow:0 4px 15px rgba(229,9,20,0.3);">➕ Create New Actor</a>
        </div>
        '''
        
    actors_grid_html = ""
    if not all_actors:
        actors_grid_html = '<div style="color:var(--muted); text-align:center; padding:60px 20px; grid-column:1/-1;">🎭 No actor profiles created yet.</div>'
    else:
        actors_grid_html = '<div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(160px, 1fr)); gap:20px;">'
        for act in all_actors:
            act_id = str(act["_id"])
            actors_grid_html += f'''
            <div style="background:var(--card); border:1px solid var(--border); border-radius:10px; overflow:hidden; transition:0.2s; cursor:pointer;" onclick="window.location.href='/actor/{act_id}'">
                <div style="position:relative; padding-top:135%; background:var(--bg3); overflow:hidden;">
                    <img src="/api/actor/photo?id={act_id}" style="position:absolute; inset:0; width:100%; height:100%; object-fit:cover;" loading="lazy">
                </div>
                <div style="padding:12px; text-align:center;">
                    <div style="font-size:14px; font-weight:700; color:var(--text); text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">{act.get('name')}</div>
                </div>
            </div>
            '''
        actors_grid_html += '</div>'

    page_body = f'''
    <div class="main" style="padding-top:30px; max-width:1100px; margin:0 auto; padding-left:20px; padding-right:20px;">
        <div style="margin-bottom:20px;">
            <h1 style="font-size:28px; font-weight:900; color:var(--text); margin-bottom:4px;">🎭 Actors Catalog</h1>
            <p style="color:var(--muted); font-size:14px;">Browse verified star profiles and linked content grids.</p>
        </div>
        {admin_header_action}
        {actors_grid_html}
    </div>
    '''
    return build_page("Actors Directory - Fast Finder", page_body, "", "actors", role)

# ─────────────────────────────────────────────────────────
# 🎭 ADMIN VIEW: CREATE ACTOR PROFILE PAGE FORM
# ─────────────────────────────────────────────────────────
@actor_routes.get('/admin/create_actor')
async def create_actor_page(req):
    role, _ = await get_auth(req)
    if role != 'admin': return web.HTTPFound('/dashboard')
        
    content = f'''
    <form action="/api/create_actor" method="post" enctype="multipart/form-data">
        <input type="text" name="name" placeholder="Actor Full Name (e.g., Shah Rukh Khan)" required>
        <textarea name="bio" placeholder="Actor Biography / Details..." style="width:100%; background:var(--bg3); border:1px solid var(--border); padding:12px; color:var(--text); border-radius:6px; min-height:100px; outline:none; margin-bottom:15px; font-family:inherit;" required></textarea>
        
        <div class="scard-label" style="margin-bottom:8px; color:var(--muted);">Actor Profile Photo</div>
        <input type="file" name="photo" accept="image/*" required style="padding:10px 0; color:var(--text);">
        
        <button class="submit-btn" type="submit" style="background:var(--accent); color:#fff; width:100%; padding:14px; border:0; border-radius:6px; font-weight:700; cursor:pointer; margin-top:10px;">Create Actor Profile</button>
    </form>
    <div style="margin-top:15px; text-align:center;"><a href="/actors" style="color:var(--muted); text-decoration:none; font-size:13px;">← Back to Actors Catalog</a></div>
    '''
    return build_page("Create Actor Profile", form_wrapper("Add New Actor", content, req.query.get('err',''), req.query.get('msg','')), "login-bg", "actors", role)

# ─────────────────────────────────────────────────────────
# ⚙️ ADMIN API: UPLOAD TO TG & SAVE TO MONGO
# ─────────────────────────────────────────────────────────
@actor_routes.post('/api/create_actor')
async def api_create_actor(req):
    role, _ = await get_auth(req)
    if role != 'admin': return web.json_response({"error": "Unauthorized"}, status=403)
        
    try:
        reader = await req.multipart()
        name, bio, image_bytes = None, None, None
        while True:
            part = await reader.next()
            if part is None: break
            if part.name == 'name': name = (await part.read()).decode().strip()
            elif part.name == 'bio': bio = (await part.read()).decode().strip()
            elif part.name == 'photo': image_bytes = await part.read()

        if not name or not bio or not image_bytes:
            return web.HTTPFound('/admin/create_actor?err=All fields are required!')

        with io.BytesIO(image_bytes) as img_buffer:
            img_buffer.name = f"{name.replace(' ', '_')}.jpg"
            msg = await temp.BOT.send_photo(chat_id=BIN_CHANNEL, photo=img_buffer)

        if not msg or not msg.photo: return web.HTTPFound('/admin/create_actor?err=Telegram Upload Failed!')
        tg_photo_id = msg.photo.sizes[-1].file_id if hasattr(msg.photo, "sizes") and msg.photo.sizes else msg.photo.file_id
        
        actor_doc = {
            "name": name,
            "bio": bio,
            "photo_url": f"TG_ID:{tg_photo_id}",
            "social_links": {"instagram": "", "youtube": "", "twitter": ""},
            "gallery": [],
            "created_at": time.time()
        }
        await actors.insert_one(actor_doc)
        return web.HTTPFound('/actors?msg=Actor Profile created successfully!')
    except Exception as e:
        return web.HTTPFound(f'/admin/create_actor?err=Server Error: {str(e)}')

# ─────────────────────────────────────────────────────────
# 🖼️ ZERO-RAM GENERAL PHOTO ENGINE (Koyeb Crash Proof)
# ─────────────────────────────────────────────────────────
@actor_routes.get('/api/actor/photo')
async def get_actor_photo(req):
    actor_id = req.query.get("id")
    img_index = req.query.get("gallery_idx") # अगर गैलरी की इमेज लोड करनी हो
    if not actor_id: return web.Response(status=400)
    
    try:
        doc = await actors.find_one({"_id": ObjectId(actor_id)})
        if not doc: return web.Response(status=404)
        
        if img_index is not None:
            idx = int(img_index)
            raw_url = doc.get("gallery", [])[idx]
        else:
            raw_url = doc.get("photo_url")
            
        if not raw_url or not raw_url.startswith("TG_ID:"): return web.Response(status=404)
        tg_id = raw_url.replace("TG_ID:", "")
        
        file_data = await temp.BOT.download_media(tg_id, in_memory=True)
        if not file_data: return web.Response(status=404)
        
        body_bytes = file_data.getvalue()
        file_data.close()
        del file_data
        
        headers = {"Cache-Control": "public, max-age=31536000, immutable", "Content-Disposition": 'inline; filename="photo.jpg"'}
        return web.Response(body=body_bytes, content_type="image/jpeg", headers=headers)
    except Exception: return web.Response(status=500)
    finally: gc.collect()

# ─────────────────────────────────────────────────────────
# 🌐 PUBLIC VIEW: ACTOR PROFILE MASTER INTERFACE
# ─────────────────────────────────────────────────────────
@actor_routes.get('/actor/{id}')
async def actor_profile_display(req):
    role, _ = await get_auth(req)
    if not role: return web.HTTPFound('/login')
    
    try:
        actor_id = req.match_info['id']
        actor = await actors.find_one({"_id": ObjectId(actor_id)})
        if not actor: return web.Response(text="Actor Not Found", status=404)
    except: return web.Response(text="Invalid ID", status=400)
        
    actor_name = actor["name"]
    social = actor.get("social_links", {"instagram": "", "youtube": "", "twitter": ""})
    gallery_list = actor.get("gallery", [])
    
    # सोशल मीडिया आइकन्स UI रेंडरिंग कवच
    social_html = '<div style="display:flex; gap:12px; margin-top:12px; flex-wrap:wrap;">'
    if social.get("instagram"): social_html += f'<a href="{social["instagram"]}" target="_blank" style="background:#ff007f; color:#fff; padding:6px 14px; border-radius:6px; text-decoration:none; font-size:12px; font-weight:700;">📸 Instagram</a>'
    if social.get("youtube"): social_html += f'<a href="{social["youtube"]}" target="_blank" style="background:#ff0000; color:#fff; padding:6px 14px; border-radius:6px; text-decoration:none; font-size:12px; font-weight:700;">📺 YouTube</a>'
    if social.get("twitter"): social_html += f'<a href="{social["twitter"]}" target="_blank" style="background:#1da1f2; color:#fff; padding:6px 14px; border-radius:6px; text-decoration:none; font-size:12px; font-weight:700;">🐦 Twitter / X</a>'
    social_html += '</div>'

    # गैलरी टैब ग्रिड रेंडरिंग इंजन
    gallery_grid_html = ""
    if role == 'admin':
        gallery_grid_html += f'''
        <div style="background:var(--card); border:1px dashed var(--border); padding:20px; border-radius:8px; text-align:center; margin-bottom:20px;">
            <form action="/api/actor/gallery_upload" method="post" enctype="multipart/form-data" style="margin:0;">
                <input type="hidden" name="actor_id" value="{actor_id}">
                <label style="background:var(--accent); color:#fff; padding:10px 20px; border-radius:6px; font-weight:700; cursor:pointer; font-size:13px; display:inline-block;">
                    📂 Add Image to Gallery
                    <input type="file" name="gallery_img" accept="image/*" style="display:none;" onchange="this.form.submit()">
                </label>
            </form>
        </div>
        '''
    if not gallery_list:
        gallery_grid_html += '<div style="color:var(--muted); text-align:center; padding:40px;">🖼️ Gallery is empty. Upload images to show here.</div>'
    else:
        gallery_grid_html += '<div class="gallery-grid">'
        for i in range(len(gallery_list)):
            gallery_grid_html += f'<img src="/api/actor/photo?id={actor_id}&gallery_idx={i}" class="gallery-item" loading="lazy">'
        gallery_grid_html += '</div>'

    # ✏️ एडमिन प्रोफाइल एडिट बटन मोडाल लेआउट ट्रिगर
    admin_edit_btn = f'<button onclick="openActorEditModal()" style="background:var(--bg4); border:1px solid var(--border); color:var(--text); padding:8px 16px; border-radius:6px; font-size:12px; font-weight:700; cursor:pointer; margin-top:10px; align-self:flex-start;">✏️ Edit Profile & Socials</button>' if role == 'admin' else ""

    tab_engine_ui = f'''
    <div class="main" style="padding-top:30px; max-width:1100px; margin: 0 auto; padding-left:20px; padding-right:20px;">
        <div style="margin-bottom:15px;"><a href="/actors" style="color:var(--muted); text-decoration:none; font-size:14px; font-weight:700;">← Back to Catalog</a></div>
        
        <div style="display:flex; gap:25px; background:var(--card); border:1px solid var(--border); padding:25px; border-radius:12px; margin-bottom:35px; flex-wrap:wrap;">
            <div style="width:160px; height:220px; background:var(--bg3); border-radius:8px; overflow:hidden; border:1px solid var(--border); flex-shrink:0;">
                <img src="/api/actor/photo?id={actor_id}" style="width:100%; height:100%; object-fit:cover;">
            </div>
            <div style="flex:1; min-width:300px; display:flex; flex-direction:column; justify-content:center;">
                <h1 style="font-size:32px; font-weight:900; color:var(--text); margin-bottom:6px;">{actor_name}</h1>
                <div style="font-size:12px; color:var(--accent); font-weight:700; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">🌟 Verified Star Profile</div>
                {social_html}
                {admin_edit_btn}
            </div>
        </div>

        <div class="actor-tab-bar">
            <button class="actor-tab active" onclick="switchActorTab(event, 'tab-info')">ℹ️ Info</button>
            <button class="actor-tab" onclick="switchActorTab(event, 'tab-video')">🎬 Video</button>
            <button class="actor-tab" onclick="switchActorTab(event, 'tab-gallery')">🖼️ Gallery</button>
        </div>

        <div id="tab-info" class="actor-panel active">
            <div style="background:var(--card); border:1px solid var(--border); padding:25px; border-radius:8px; line-height:1.7; color:var(--text); font-size:15px; white-space:pre-line;">
                {actor["bio"]}
            </div>
        </div>

        <div id="tab-video" class="actor-panel">
            <div style="display:flex; gap:10px; margin-bottom:20px; flex-wrap:wrap; align-items:center;">
                <div style="flex:1; min-width:200px; display:flex; background:var(--bg3); border:1px solid var(--border); border-radius:8px; padding:0 12px; align-items:center;">
                    <input type="text" id="actor_movie_q" value="{actor_name}" placeholder="Search inside actor movies..." style="width:100%; background:transparent; border:none; padding:10px 0; color:var(--text); outline:none; font-size:14px; font-weight:600;">
                </div>
                <select id="actor_col_sel" onchange="resetActorSearchPage()" style="background:var(--bg3); color:var(--text); border:1px solid var(--border); padding:10px 14px; border-radius:8px; font-weight:700; outline:none; cursor:pointer;">
                    <option value="all">📂 All Collections</option>
                    <option value="primary">🟢 Primary</option>
                    <option value="cloud">🔵 Cloud</option>
                    <option value="archive">🟠 Archive</option>
                </select>
                <select id="actor_mode_sel" onchange="resetActorSearchPage()" style="background:var(--bg3); color:var(--text); border:1px solid var(--border); padding:10px 14px; border-radius:8px; font-weight:700; outline:none; cursor:pointer;">
                    <option value="tg">🖼️ Original TG Thumb</option>
                    <option value="none">⚡ Text Only (Fastest)</option>
                </select>
                <button onclick="triggerActorSearchAjax()" style="background:var(--accent); color:#fff; border:none; padding:11px 24px; border-radius:8px; font-weight:700; cursor:pointer;">Filter</button>
            </div>

            <div id="actor_video_results" class="res-grid"></div>
            
            <div class="pagination" id="actor_page_box" style="display:none; justify-content:center; gap:12px; margin-top:20px;">
                <button class="pg-btn" id="actor_pBtn" onclick="actorPagePrev()">Previous</button>
                <span class="pg-info" id="actor_pgInfo">Page 1</span>
                <button class="pg-btn" id="actor_nBtn" onclick="actorPageNext()">Next</button>
            </div>
        </div>

        <div id="tab-gallery" class="actor-panel">
            {gallery_grid_html}
        </div>
    </div>

    <div class="edit-modal" id="actorEditModal" onclick="if(event.target===this)closeActorEditModal()">
        <div class="em-card" style="max-width:550px;">
            <button class="em-close" onclick="closeActorEditModal()">&#10005;</button>
            <div class="em-title">✏️ Edit Actor Profile Matrix</div>
            <form action="/api/actor/update_profile" method="post">
                <input type="hidden" name="actor_id" value="{actor_id}">
                
                <div class="scard-label">Actor Full Name</div>
                <input type="text" name="name" value="{actor_name}" class="em-input" required>
                
                <div class="scard-label">Biography Details</div>
                <textarea name="bio" class="em-input" style="min-height:120px; font-family:inherit; padding:10px; line-height:1.5;" required>{actor["bio"]}</textarea>
                
                <div class="em-title" style="font-size:14px; margin-top:15px; margin-bottom:10px;">🌐 Social Media Channels Matrix</div>
                
                <div class="scard-label">Instagram Link</div>
                <input type="url" name="insta" value="{social.get('instagram','')}" placeholder="https://instagram.com/..." class="em-input">
                
                <div class="scard-label">YouTube Channel Link</div>
                <input type="url" name="yt" value="{social.get('youtube','')}" placeholder="https://youtube.com/..." class="em-input">
                
                <div class="scard-label">Twitter / X Profile Link</div>
                <input type="url" name="twitter" value="{social.get('twitter','')}" placeholder="https://x.com/..." class="em-input">
                
                <button class="em-save-btn" type="submit">Save Changes & Sync Grid</button>
            </form>
        </div>
    </div>

    <script>
        var actName = "{actor_name}";
        var actCurPage = 1, actOffset = 0, actNextOffset = "";
        var actLimit = 21; // 21 रिज़ल्ट्स स्ट्रिक्ट बाउंडेड

        function switchActorTab(evt, tabId) {{
            var panels = document.querySelectorAll('.actor-panel');
            for (var i = 0; i < panels.length; i++) {{ panels[i].classList.remove('active'); }}
            var tabs = document.querySelectorAll('.actor-tab');
            for (var j = 0; j < tabs.length; j++) {{ tabs[j].classList.remove('active'); }}
            document.getElementById(tabId).classList.add('active');
            evt.currentTarget.classList.add('active');
            if(tabId === 'tab-video' && document.getElementById('actor_video_results').innerHTML === "") {{
                triggerActorSearchAjax();
            }}
        }}

        function openActorEditModal() {{ document.getElementById('actorEditModal').classList.add('open'); }}
        function closeActorEditModal() {{ document.getElementById('actorEditModal').classList.remove('open'); }}
        function resetActorSearchPage() {{ actCurPage = 1; actOffset = 0; }}

        async function triggerActorSearchAjax() {{
            var q = document.getElementById('actor_movie_q').value.trim() || actName;
            var col = document.getElementById('actor_col_sel').value;
            var mode = document.getElementById('actor_mode_sel').value;
            var grid = document.getElementById('actor_video_results');
            
            grid.className = 'res-grid mode-' + mode;
            grid.innerHTML = '<div class="spin-wrap"><div class="spinner"></div><span>Filtering Network Matrix...</span></div>';
            
            try {{
                var r = await fetch('/api/search?q=' + encodeURIComponent(q) + '&offset=' + actOffset + '&col=' + col + '&mode=' + mode);
                var d = await r.json();
                if(!d.results || !d.results.length) {{
                    grid.innerHTML = '<div class="empty"><p>No video assets matching filters found inside database.</p></div>';
                    document.getElementById('actor_page_box').style.display = 'none';
                    return;
                }}
                var h = '';
                d.results.forEach(function(f) {{
                    var sc = (f.source || 'primary').toLowerCase();
                    var posterHtml = '';
                    if(mode !== 'none') {{
                        posterHtml = '<div class="poster-box"><img src="'+f.tg_thumb+'" class="fc-poster loaded" loading="lazy"><div class="poster-top"><span class="type-chip">'+f.type.toUpperCase()+'</span><span class="size-chip">'+f.size+'</span><span class="source-pill '+sc+'"><span class="source-dot"></span>'+sc.toUpperCase()+'</span></div></div>';
                    }} else {{
                        posterHtml = '<div class="fc-text-info"><span class="tc-type">'+f.type.toUpperCase()+'</span><span class="tc-size">'+f.size+'</span><span class="source-pill '+sc+'" style="margin-left:auto"><span class="source-dot"></span>'+sc.toUpperCase()+'</span></div>';
                    }}
                    h += '<div class="file-card">' + posterHtml + '<div class="fc-body"><div class="fc-name" onclick="window.open(\''+f.watch+'\',\'_blank\')">'+f.name+'</div></div></div>';
                }});
                grid.innerHTML = h;
                actNextOffset = d.next_offset;
                document.getElementById('actor_page_box').style.display = 'flex';
                document.getElementById('actor_pBtn').disabled = (actOffset === 0);
                document.getElementById('actor_nBtn').disabled = !actNextOffset;
                document.getElementById('actor_pgInfo').textContent = 'Page ' + actCurPage;
            }} catch(e) {{
                grid.innerHTML = '<div class="empty"><p>Matrix pipeline sync timeout error.</p></div>';
            }}
        }}

        function actorPageNext() {{ if(actNextOffset) {{ actCurPage++; actOffset = actNextOffset; triggerActorSearchAjax(); window.scrollTo(0,350); }} }}
        function actorPagePrev() {{ if(actCurPage > 1) {{ actCurPage--; actOffset = Math.max(0, actOffset - actLimit); triggerActorSearchAjax(); window.scrollTo(0,350); }} }}
        
        document.getElementById('actor_movie_q').addEventListener('keydown', function(e) {{ if(e.key === 'Enter') {{ resetActorSearchPage(); triggerActorSearchAjax(); }} }});
    </script>
    <style>
        .actor-tab-bar {{ display: flex; gap: 10px; border-bottom: 2px solid var(--border); margin-bottom: 25px; }}
        .actor-tab {{ background: transparent; border: none; color: var(--muted); padding: 12px 20px; font-size: 15px; font-weight: 700; cursor: pointer; transition: 0.2s; position: relative; font-family: inherit; }}
        .actor-tab.active {{ color: var(--text); }}
        .actor-tab.active::after {{ content: ''; position: absolute; bottom: -2px; left: 0; right: 0; height: 2px; background: var(--accent); }}
        .actor-panel {{ display: none; }}
        .actor-panel.active {{ display: block; }}
        .gallery-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }}
        .gallery-item {{ width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px; border: 1px solid var(--border); transition: transform 0.2s; }}
        .gallery-item:hover {{ transform: scale(1.03); }}
    </style>
    '''
    return build_page(f"{actor_name} - Profile Matrix", tab_engine_ui, "", "actors", role)

# ─────────────────────────────────────────────────────────
# ⚙️ ADMIN API: UPDATE PROFILE DETAILS & SOCIAL MEDIA CHANNELS
# ─────────────────────────────────────────────────────────
@actor_routes.post('/api/actor/update_profile')
async def api_actor_update_profile(req):
    role, _ = await get_auth(req)
    if role != 'admin': return web.json_response({"error": "Unauthorized"}, status=403)
    
    d = await req.post()
    actor_id = d.get('actor_id')
    name = d.get('name', '').strip()
    bio = d.get('bio', '').strip()
    insta = d.get('insta', '').strip()
    yt = d.get('yt', '').strip()
    twitter = d.get('twitter', '').strip()
    
    if not actor_id or not name or not bio: return web.HTTPFound('/actors?err=Missing assets data')
    
    update_doc = {
        "name": name,
        "bio": bio,
        "social_links": {"instagram": insta, "youtube": yt, "twitter": twitter}
    }
    
    await actors.update_one({"_id": ObjectId(actor_id)}, {"$set": update_doc})
    return web.HTTPFound(f'/actor/{actor_id}?msg=Profile and Social Networks synced successfully!')

# ─────────────────────────────────────────────────────────
# 🖼️ ADMIN API: UPLOAD NATIVE IMAGE TO GALLERY (NO RAM CACHE BLAST)
# ─────────────────────────────────────────────────────────
@actor_routes.post('/api/actor/gallery_upload')
async def api_actor_gallery_upload(req):
    role, _ = await get_auth(req)
    if role != 'admin': return web.json_response({"error": "Unauthorized"}, status=403)
    
    try:
        reader = await req.multipart()
        actor_id, image_bytes = None, None
        while True:
            part = await reader.next()
            if part is None: break
            if part.name == 'actor_id': actor_id = (await part.read()).decode().strip()
            elif part.name == 'gallery_img': image_bytes = await part.read()
            
        if not actor_id or not image_bytes: return web.HTTPFound('/actors?err=Assets reading packet failure')
        
        with io.BytesIO(image_bytes) as img_buffer:
            img_buffer.name = f"gallery_{actor_id}_{int(time.time())}.jpg"
            msg = await temp.BOT.send_photo(chat_id=BIN_CHANNEL, photo=img_buffer)
            
        if not msg or not msg.photo: return web.HTTPFound(f'/actor/{actor_id}?err=Telegram Node Gallery Upload Failed')
        tg_photo_id = msg.photo.sizes[-1].file_id if hasattr(msg.photo, "sizes") and msg.photo.sizes else msg.photo.file_id
        
        # डॉक्यूमेंट के गैलरी एरे के अंदर $push कर दो
        await actors.update_one({"_id": ObjectId(actor_id)}, {"$push": {"gallery": f"TG_ID:{tg_photo_id}"}})
        return web.HTTPFound(f'/actor/{actor_id}?msg=New portrait uploaded successfully to star gallery!')
    except Exception as e:
        return web.HTTPFound(f'/actors?err=System core crash: {str(e)}')

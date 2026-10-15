const $=s=>document.querySelector(s);
const el=(t,c,x)=>{const n=document.createElement(t);if(c)n.className=c;if(x!=null)n.textContent=x;return n;};
const J=async(u,o)=>{const r=await fetch(u,o);let d={};try{d=await r.json()}catch{}
  if(r.status===401)location.href="/login";return {ok:r.ok,d};};

document.querySelectorAll("[data-open]").forEach(b=>b.onclick=()=>$("#"+b.dataset.open).showModal());
const buy=$("#buy"); if(buy) buy.onclick=async()=>{await J("/api/premium",{method:"POST"});location.reload();};

// projects
async function loadProjects(){
  const {d}=await J("/api/projects"); const ul=$("#plist"); ul.replaceChildren();
  if(!d.length){ul.append(el("li","mute","No projects yet. Add your first one above."));return;}
  d.forEach(p=>{const li=el("li","proj"); const h=el("div","ph");
    h.append(el("strong",null,p.name),el("span","mute small",p.created));
    li.append(h); if(p.details) li.append(el("p","mute",p.details));
    const f=el("div","pf");
    if(p.filename){const a=el("a","link",p.filename);a.href="/files/"+p.id;f.append(a);}
    const x=el("button","link danger","Delete");
    x.onclick=async()=>{if(confirm("Delete "+p.name+"?")){await J("/api/projects/"+p.id,{method:"DELETE"});loadProjects();}};
    f.append(x);li.append(f);ul.append(li);});
}
$("#pf").querySelector("input[type=file]").onchange=e=>{$("#fn").textContent=e.target.files[0]?.name||"Attach a file (optional)";};
$("#pf").onsubmit=async e=>{e.preventDefault();$("#perr").textContent="";
  const {ok,d}=await J("/api/projects",{method:"POST",body:new FormData(e.target)});
  if(!ok){$("#perr").textContent=d.error;if(d.premium)$("#premium").showModal();return;}
  e.target.reset();$("#fn").textContent="Attach a file (optional)";loadProjects();};

// chat
const hist=[];
function say(t,c){const m=el("div","msg "+c,t);$("#log").append(m);$("#log").scrollTop=1e9;return m;}
$("#cf").onsubmit=async e=>{e.preventDefault();const t=$("#ci").value.trim();if(!t)return;
  $("#ci").value="";say(t,"me");hist.push({role:"user",content:t});
  const w=say("Thinking…","bot wait");
  const {d}=await J("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({messages:hist})});
  w.classList.remove("wait");w.textContent=d.reply||d.error||"Something went wrong.";
  if(d.reply)hist.push({role:"assistant",content:d.reply});};

// comments
function drawComments(d){const ul=$("#clist");ul.replaceChildren();
  if(!d.length){ul.append(el("li","mute","No comments yet. Start the conversation."));return;}
  d.forEach(c=>{const li=el("li","cm");const h=el("div","ph");
    h.append(el("strong",null,c.username),el("span","mute small",c.created.slice(0,16)));
    li.append(h,el("p",null,c.body));ul.append(li);});}
$("#mf").onsubmit=async e=>{e.preventDefault();
  const {ok,d}=await J("/api/comments",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({body:$("#mi").value})});
  if(ok){$("#mi").value="";drawComments(d);}};
loadProjects(); J("/api/comments").then(r=>drawComments(r.d));

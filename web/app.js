const KEY = "scholarTrackerPrototypeV1";
const today = () => new Date().toLocaleDateString("en-CA");
const initial = {
  classes: [
    {id:"g7a",name:"Grade 7",stream:"East",teacher:"Mr. Otieno"},
    {id:"g7b",name:"Grade 7",stream:"West",teacher:"Ms. Achieng"},
    {id:"g8a",name:"Grade 8",stream:"East",teacher:"Mrs. Wanjiku"},
    {id:"g8b",name:"Grade 8",stream:"West",teacher:"Mr. Kamau"},
    {id:"g9a",name:"Grade 9",stream:"East",teacher:"Ms. Njeri"}
  ],
  students: [
    {id:1,name:"Amina Otieno",adm:"ST-001",classId:"g7a",parent:"Jane Otieno"},
    {id:2,name:"Brian Kiptoo",adm:"ST-002",classId:"g7a",parent:"Peter Kiptoo"},
    {id:3,name:"Faith Wanjiku",adm:"ST-003",classId:"g7b",parent:"Mary Wanjiku"},
    {id:4,name:"Kevin Mwangi",adm:"ST-004",classId:"g8a",parent:"David Mwangi"},
    {id:5,name:"Lydia Achieng",adm:"ST-005",classId:"g8b",parent:"Rose Achieng"},
    {id:6,name:"Mark Njoroge",adm:"ST-006",classId:"g8a",parent:"Ann Njoroge"},
    {id:7,name:"Neema Hassan",adm:"ST-007",classId:"g9a",parent:"Ali Hassan"},
    {id:8,name:"Peter Barasa",adm:"ST-008",classId:"g9a",parent:"Susan Barasa"}
  ],
  attendance: {},
  events: [
    {id:1,title:"Term planning meeting",date:"2026-11-24",type:"Meeting",details:"Staff and school leadership"},
    {id:2,title:"Continuous assessment",date:"2026-11-27",type:"Academic",details:"Check the class timetable"},
    {id:3,title:"Games afternoon",date:"2026-12-02",type:"Sports",details:"School field"}
  ]
};
let data;
try { data = JSON.parse(localStorage.getItem(KEY)) || structuredClone(initial); } catch { data = structuredClone(initial); }
let selectedAttendanceClass = "all";
let toastTimer;
const $ = id => document.getElementById(id);
const classLabel = c => c ? c.name + " " + c.stream : "Unassigned";
const getClass = id => data.classes.find(c => c.id === id);
const keyFor = (date,id) => date + ":" + id;
const statusFor = (date,id) => data.attendance[keyFor(date,id)] || "Unmarked";
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(data)); } catch {} };
const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const initials = name => name.split(/\s+/).slice(0,2).map(s=>s[0]||"").join("").toUpperCase();
function toast(message){ $("toast").textContent=message; $("toast").classList.add("show"); clearTimeout(toastTimer); toastTimer=setTimeout(()=>$("toast").classList.remove("show"),2600); }
function optionsForClasses(selected="all",includeAll=false){ return (includeAll?'<option value="all">All classes</option>':"")+data.classes.map(c=>'<option value="'+esc(c.id)+'" '+(c.id===selected?"selected":"")+'>'+esc(classLabel(c))+'</option>').join(""); }
function fillSelects(){
  ["attendanceClass","studentClass","reportClass"].forEach(id=>{const el=$(id);if(!el)return;const old=el.value;el.innerHTML=optionsForClasses(id==="attendanceClass"?"all":id==="reportClass"?"all":"",id!=="studentClass");if([...el.options].some(o=>o.value===old))el.value=old;});
  $("parentStudent").innerHTML=data.students.map(s=>'<option value="'+s.id+'">'+esc(s.name)+' — '+esc(s.adm)+'</option>').join("");
}
function markedCounts(date,students=data.students){let present=0,absent=0;students.forEach(s=>{const st=statusFor(date,s.id);if(st==="Present")present++;if(st==="Absent")absent++;});return {present,absent,unmarked:students.length-present-absent};}
function renderDashboard(){
  $("statStudents").textContent=data.students.length;$("statClasses").textContent=data.classes.length;
  const counts=markedCounts(today());$("statPresent").textContent=counts.present;$("statAbsent").textContent=counts.absent;
  $("presentSub").textContent=counts.unmarked?counts.unmarked+" not marked yet":"All students marked";
  const recent=data.students.slice(0,5);
  $("dashboardAttendance")= $("dashboardAttendance");
  $("dashboardAttendance").innerHTML=recent.length?recent.map(s=>'<div class="mini-row"><div class="student-avatar">'+esc(initials(s.name))+'</div><div class="mini-info"><strong>'+esc(s.name)+'</strong><small>'+esc(s.adm)+' · '+esc(classLabel(getClass(s.classId)))+'</small></div>'+statusBadge(statusFor(today(),s.id))+'</div>').join(""):'<div class="empty-state">Add students to get started.</div>';
}
function statusBadge(status){const cls=status==="Present"?"present":status==="Absent"?"absent":"unmarked";return '<span class="status '+cls+'">'+esc(status)+'</span>';}
function renderAttendance(){
  const date=$("attendanceDate").value||today(), classId=$("attendanceClass").value;
  const list=data.students.filter(s=>classId==="all"||s.classId===classId);
  const counts=markedCounts(date,list);
  $("attendanceSummary").innerHTML='<span class="summary-pill">Students <strong>'+list.length+'</strong></span><span class="summary-pill">Present <strong>'+counts.present+'</strong></span><span class="summary-pill">Absent <strong>'+counts.absent+'</strong></span><span class="summary-pill">Unmarked <strong>'+counts.unmarked+'</strong></span>';
  $("attendanceRows").innerHTML=list.length?list.map(s=>'<tr><td><span class="table-name">'+esc(s.name)+'</span><span class="table-sub">'+esc(s.parent||"Parent not added")+'</span></td><td>'+esc(s.adm)+'</td><td>'+esc(classLabel(getClass(s.classId)))+'</td><td><select class="status-select attendance-select" data-student="'+s.id+'" aria-label="Attendance status for '+esc(s.name)+'"><option '+(statusFor(date,s.id)==="Unmarked"?"selected":"")+' value="Unmarked">Unmarked</option><option '+(statusFor(date,s.id)==="Present"?"selected":"")+' value="Present">Present</option><option '+(statusFor(date,s.id)==="Absent"?"selected":"")+' value="Absent">Absent</option></select></td></tr>').join(""):'<tr><td colspan="4" class="empty-state">No students in this selection.</td></tr>';
}
function renderStudents(){
 const query=$("studentSearch").value.trim().toLowerCase();
 const list=data.students.filter(s=>(s.name+" "+s.adm+" "+classLabel(getClass(s.classId))).toLowerCase().includes(query));
 $("studentCount").textContent=list.length+" students";
 $("studentRows").innerHTML=list.length?list.map(s=>'<tr><td><span class="table-name">'+esc(s.name)+'</span></td><td>'+esc(s.adm)+'</td><td>'+esc(classLabel(getClass(s.classId)))+'</td><td>'+esc(s.parent||"—")+'</td><td>'+statusBadge(statusFor(today(),s.id))+'</td></tr>').join(""):'<tr><td colspan="5" class="empty-state">No students found.</td></tr>';
}
function renderClasses(){
 $("classCards").innerHTML=data.classes.map(c=>'<article class="stat-card"><div class="stat-top"><span>'+esc(c.stream)+' stream</span><span class="stat-icon blue">▤</span></div><strong>'+data.students.filter(s=>s.classId===c.id).length+'</strong><small>'+esc(c.name)+' · '+esc(c.teacher)+'</small></article>').join("");
 $("classRows").innerHTML=data.classes.map(c=>'<tr><td><span class="class-name">'+esc(c.name)+'</span></td><td>'+esc(c.stream)+'</td><td>'+data.students.filter(s=>s.classId===c.id).length+'</td><td>'+esc(c.teacher)+'</td></tr>').join("");
}
function renderParent(){
 const s=data.students.find(x=>String(x.id)===$("parentStudent").value)||data.students[0];
 if(!s){$("parentSummary").innerHTML='<div class="empty-state">Add a student to preview the parent portal.</div>';return;}
 const c=getClass(s.classId),st=statusFor(today(),s.id);
 $("parentSummary").innerHTML='<div class="parent-child"><div class="student-avatar">'+esc(initials(s.name))+'</div><div><h2>'+esc(s.name)+'</h2><p class="muted">'+esc(s.adm)+' · '+esc(classLabel(c))+'</p></div></div><div class="parent-detail"><strong>Attendance today</strong>'+statusBadge(st)+'<p style="margin-top:8px">For corrections, contact the school office.</p></div><div class="parent-detail"><strong>Parent / guardian</strong><p>'+esc(s.parent||"Not added")+'</p></div><div class="parent-detail"><strong>Next school event</strong><p>'+esc(data.events.filter(e=>e.date>=today()).sort((a,b)=>a.date.localeCompare(b.date))[0]?.title||"No upcoming events")+'</p></div>';
}
function renderEvents(){
 const events=[...data.events].sort((a,b)=>a.date.localeCompare(b.date));
 $("eventList").innerHTML=events.length?events.map(e=>{const d=new Date(e.date+"T12:00:00");return '<div class="event-item"><div class="event-date"><strong>'+d.getDate()+'</strong><small>'+d.toLocaleDateString("en-KE",{month:"short"})+'</small></div><div class="event-info"><strong>'+esc(e.title)+'</strong><p>'+esc(e.details||"No extra details")+'</p></div><span class="event-type">'+esc(e.type)+'</span></div>';}).join(""):'<div class="empty-state">No events yet. Add your first school event.</div>';
}
function renderReports(){
 const date=$("reportDate").value||today(),classId=$("reportClass").value||"all";
 const list=data.students.filter(s=>classId==="all"||s.classId===classId),counts=markedCounts(date,list),marked=counts.present+counts.absent;
 $("reportStudents").textContent=list.length;$("reportPresent").textContent=counts.present;$("reportAbsent").textContent=counts.absent;$("reportRate").textContent=marked?Math.round(counts.present/marked*100)+"%":"—";
 $("reportRows").innerHTML=list.map(s=>'<tr><td>'+esc(s.name)+'</td><td>'+esc(s.adm)+'</td><td>'+esc(classLabel(getClass(s.classId)))+'</td><td>'+statusBadge(statusFor(date,s.id))+'</td></tr>').join("")||'<tr><td colspan="4" class="empty-state">No student records.</td></tr>';
}
function renderAll(){fillSelects();renderDashboard();renderAttendance();renderStudents();renderClasses();renderParent();renderEvents();renderReports();}
function showPage(name){const valid=["dashboard","attendance","students","classes","parents","calendar","reports"].includes(name)?name:"dashboard";document.querySelectorAll(".page").forEach(p=>p.classList.toggle("active",p.id==="page-"+valid));document.querySelectorAll(".nav-link").forEach(a=>a.classList.toggle("active",a.dataset.page===valid));const link=document.querySelector('[data-page="'+valid+'"]');$("pageCrumb").textContent=link?link.textContent.trim():"Overview";$("sidebar").classList.remove("open");if(valid==="attendance")renderAttendance();if(valid==="reports")renderReports();}
document.querySelectorAll("[data-page]").forEach(a=>a.addEventListener("click",e=>{e.preventDefault();location.hash=a.dataset.page;showPage(a.dataset.page);}));
document.querySelectorAll("[data-go]").forEach(b=>b.addEventListener("click",()=>{location.hash=b.dataset.go;showPage(b.dataset.go);}));
window.addEventListener("hashchange",()=>showPage(location.hash.slice(1)));
$("menuToggle").addEventListener("click",()=>$("sidebar").classList.toggle("open"));
$("todayButton").addEventListener("click",()=>{location.hash="attendance";$("attendanceDate").value=today();showPage("attendance");});
$("dismissNotice").addEventListener("click",()=>document.querySelector(".notice").classList.add("hidden"));
$("attendanceClass").addEventListener("change",renderAttendance);$("attendanceDate").addEventListener("change",renderAttendance);
$("attendanceRows").addEventListener("change",e=>{if(!e.target.matches(".attendance-select"))return;const date=$("attendanceDate").value||today();data.attendance[keyFor(date,Number(e.target.dataset.student))]=e.target.value;save();renderAttendance();renderDashboard();renderStudents();renderParent();renderReports();});
$("saveAttendance").addEventListener("click",()=>{save();toast("Attendance register saved in this browser.");renderAll();});
$("resetAttendance").addEventListener("click",()=>{if(!confirm("Clear attendance marks for the selected date?"))return;const date=$("attendanceDate").value||today();data.students.forEach(s=>delete data.attendance[keyFor(date,s.id)]);save();renderAll();toast("Attendance marks cleared.");});
$("showStudentForm").addEventListener("click",()=>$("studentFormPanel").classList.toggle("hidden"));
$("cancelStudent").addEventListener("click",()=>{$("studentForm").reset();$("studentFormPanel").classList.add("hidden");});
$("studentSearch").addEventListener("input",renderStudents);
$("studentForm").addEventListener("submit",e=>{e.preventDefault();const name=$("studentName").value.trim(),adm=$("studentAdm").value.trim();if(data.students.some(s=>s.adm.toLowerCase()===adm.toLowerCase())){toast("That admission number is already in use.");return;}data.students.push({id:Math.max(0,...data.students.map(s=>s.id))+1,name,adm,classId:$("studentClass").value,parent:$("parentName").value.trim()});save();$("studentForm").reset();$("studentFormPanel").classList.add("hidden");renderAll();toast("Demo student added.");});
$("parentStudent").addEventListener("change",renderParent);
$("showEventForm").addEventListener("click",()=>$("eventFormPanel").classList.toggle("hidden"));
$("cancelEvent").addEventListener("click",()=>{$("eventForm").reset();$("eventFormPanel").classList.add("hidden");});
$("eventForm").addEventListener("submit",e=>{e.preventDefault();data.events.push({id:Math.max(0,...data.events.map(x=>x.id))+1,title:$("eventTitle").value.trim(),date:$("eventDate").value,type:$("eventType").value,details:$("eventDetails").value.trim()});save();$("eventForm").reset();$("eventFormPanel").classList.add("hidden");renderAll();toast("School event added.");});
$("reportDate").addEventListener("change",renderReports);$("reportClass").addEventListener("change",renderReports);
$("downloadReport").addEventListener("click",()=>{const date=$("reportDate").value||today(),classId=$("reportClass").value||"all",list=data.students.filter(s=>classId==="all"||s.classId===classId);const rows=[["Date","Student","Admission number","Class","Status"],...list.map(s=>[date,s.name,s.adm,classLabel(getClass(s.classId)),statusFor(date,s.id)])];const csv=rows.map(r=>r.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(",")).join("\r\n");const blob=new Blob([csv],{type:"text/csv;charset=utf-8;"}),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download="scholar-tracker-attendance-"+date+".csv";a.click();URL.revokeObjectURL(url);});
$("attendanceDate").value=today();$("reportDate").value=today();$("eventDate").value=today();renderAll();showPage(location.hash.slice(1));
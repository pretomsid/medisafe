/* API layer: frontend আর backend-এর মধ্যে একমাত্র যোগাযোগের জায়গা।
   UI কোড কখনো সরাসরি fetch করে না, শুধু API.xxx() ডাকে।
   Backend-এর URL বা নিয়ম বদলালে শুধু এই ফাইল বদলালেই হবে। */
const API={
BASE:window.MEDISAFE_API_BASE||'/api',   // backend আলাদা server-এ গেলে শুধু এটা বদলান
delay:ms=>new Promise(r=>setTimeout(r,ms)),

async req(method,path,body){
 const opt={method,credentials:'include',headers:{}};
 if(body instanceof FormData)opt.body=body;
 else if(body!==undefined){opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body)}
 const down='Cannot reach the MediSafe backend. Start it with "python run.py" in the backend folder and open http://127.0.0.1:5000 (or http://127.0.0.1:8000)';
 let r;try{r=await fetch(this.BASE+path,opt)}catch{throw new Error(down)}
 const json=(r.headers.get('content-type')||'').includes('application/json');
 if(!json){
   const text=await r.text().catch(()=>'');
   throw new Error('Server returned error ('+r.status+'): '+(text.slice(0,120)||down));
 }
 const data=json?await r.json():{};
 if(r.status==401&&!path.startsWith('/auth/')){location.href='auth.html#login';throw new Error('Please log in')}
 if(!r.ok){const e=new Error(data.error||'Request failed');e.status=r.status;throw e}
 return data},

list(key){return this.req('GET','/'+key)},                     // user, records, meds, catalog, notifications, activity
async auth(kind,data){
 if(kind=='forgot'||kind=='reset')return {ok:true,demo:true}; // email পাঠানো পরের version-এ
 return this.req('POST','/auth/'+kind,data)},
logout(){return this.req('POST','/auth/logout')},
changePassword(current,next){return this.req('POST','/auth/change-password',{current,new:next})},
saveProfile(d){return this.req('PUT','/user',d)},
addMed(d){return this.req('POST','/meds',d)},
updateMed(id,d){return this.req('PUT','/meds/'+id,d)},
deleteMed(id){return this.req('DELETE','/meds/'+id)},
uploadRecord(formData){return this.req('POST','/records',formData)},
extractRecord(id){return this.req('POST','/records/'+id+'/extract')},
safetyReport(extra=[]){return this.req('POST','/interactions/report',{extra})},
importMeds(id,items){return this.req('POST','/records/'+id+'/import-meds',{items})},
deleteRecord(id){return this.req('DELETE','/records/'+id)},
recordFileUrl(id){return this.BASE+'/records/'+id+'/file'},
readAllNotifications(){return this.req('POST','/notifications/read-all')},
searchCatalog(q='',form='',limit=30){return this.req('GET','/catalog?'+new URLSearchParams({q,form,limit}))},
catalogForms(){return this.req('GET','/catalog/forms')},
alternatives(id){return this.req('GET','/alternatives/'+id)},
catalogLive(id){return this.req('GET','/catalog/'+id+'/live')},
modelInfo(){return this.req('GET','/model-info')},
checkInteraction(items){return this.req('POST','/interactions/check',{items:items.map(m=>m.id)})}};

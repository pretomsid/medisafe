const $=s=>document.querySelector(s);
const R={req:v=>v.trim()?'':'This field is required',email:v=>/^\S+@\S+\.\S+$/.test(v)?'':'Enter a valid email address',phone:v=>/^(\+?88)?01[3-9]\d{8}$/.test(v.replace(/[\s-]/g,''))?'':'Enter a valid Bangladeshi phone number',pw:v=>v.length>=8&&/[A-Za-z]/.test(v)&&/\d/.test(v)?'':'Use 8+ characters with a letter and a number'};
const F=(n,l,t,v,p='')=>`<div class="mb-3"><label class="form-label">${l}</label><div class="input-group has-validation"><input class="form-control" id="${n}" name="${n}" type="${t}" data-v="${v}" placeholder="${p}" autocomplete="off">${t=='password'?'<button type="button" class="btn btn-outline-secondary" data-eye="'+n+'" aria-label="Show password"><i class="bi bi-eye"></i></button>':''}<div class="invalid-feedback"></div></div></div>`;
const P={login:['Welcome back','Log in to your MediSafe account',F('email','Email','email','req email','you@example.com')+F('password','Password','password','req')+'<div class="text-end mb-3"><a href="#forgot">Forgot password?</a></div>','Log In','<a href="#register">Create an account</a>'],
register:['Create your account','Start organizing your medical records',F('name','Full Name','text','req')+F('email','Email','email','req email')+F('phone','Phone Number','tel','req phone','01XXXXXXXXX')+F('password','Password','password','req pw')+F('confirm','Confirm Password','password','req match:#password'),'Register','Already registered? <a href="#login">Log in</a>'],
forgot:['Forgot password','Enter your email to receive a reset link',F('email','Email','email','req email'),'Send Reset Link','<a href="#login">Back to login</a>'],
reset:['Reset password','Choose a new password',F('password','New Password','password','req pw')+F('confirm','Confirm Password','password','req match:#password'),'Reset Password','<a href="#login">Back to login</a>']};
function check(el){let m='';for(const r of el.dataset.v.split(' ')){m=r.startsWith('match:')?(el.value===$(r.slice(6)).value?'':'Passwords do not match'):R[r](el.value);if(m)break}
el.classList.toggle('is-invalid',!!m);el.classList.toggle('is-valid',!m&&!!el.value);el.parentElement.querySelector('.invalid-feedback').textContent=m;return !m}
function show(){const k=P[location.hash.slice(1)]?location.hash.slice(1):'login',p=P[k];
$('#box').innerHTML=`<h4>${p[0]}</h4><p class="text-muted">${p[1]}</p><div id="msg"></div><form id="f" novalidate>${p[2]}<button class="btn btn-primary w-100" id="go">${p[3]}</button></form><p class="text-center small mt-3 mb-0">${p[4]}</p>`;
$('#f').onsubmit=async e=>{e.preventDefault();const ok=[...e.target.querySelectorAll('input')].map(check).every(Boolean);if(!ok)return;
const b=$('#go');b.disabled=true;b.innerHTML='<span class="spinner-border spinner-border-sm"></span> Please wait';
try{await API.auth(k,Object.fromEntries(new FormData(e.target)));
if(k=='login'||k=='register'){$('#msg').innerHTML='<div class="alert alert-success">Success. Redirecting…</div>';setTimeout(()=>location.href='app.html',900)}
else{$('#msg').innerHTML='<div class="alert alert-success">'+(k=='forgot'?'If this email is registered, a reset link will be sent (demo).':'Password reset (demo). You can log in now.')+'</div>';b.disabled=false;b.textContent=p[3]}}
catch(err){$('#msg').innerHTML='<div class="alert alert-danger"></div>';$('#msg .alert').textContent=err.message||'Something went wrong. Please try again.';b.disabled=false;b.textContent=p[3]}};
$('#f').oninput=e=>e.target.dataset.v&&e.target.classList.contains('is-invalid')&&check(e.target)}
document.addEventListener('click',e=>{const b=e.target.closest('[data-eye]');if(!b)return;const i=$('#'+b.dataset.eye);i.type=i.type=='password'?'text':'password';b.firstChild.className='bi bi-eye'+(i.type=='text'?'-slash':'')});
addEventListener('hashchange',show);show();

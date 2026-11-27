export const SCENARIOS = {
  identity: {label:'Identity + hidden data',name:'identity-proof.pdf',kind:'Identity document',size:'184 KB',title:'Identity proof',subtitle:'Fictional identity document',number:'2345 6789 0124',author:'Sample Applicant',destination:'https://files.scholarship-storage.example/upload',crossOrigin:true,findings:[{id:'aadhaar',label:'Full identity number',value:'•••• •••• 0124',kind:'Visible information',why:'The file reveals all 12 digits. Check whether the portal accepts a copy with only the last four visible.',action:'Mask the first eight digits'},{id:'author',label:'PDF author metadata',value:'Sample Applicant',kind:'Hidden information',why:'An author property can reveal information that is not visible on the document page.',action:'Remove author metadata'}],signed:false},
  clean: {label:'Clean document',name:'enrolment-confirmation.pdf',kind:'Enrolment confirmation',size:'96 KB',title:'Enrolment confirmation',subtitle:'Fictional academic record',number:'STUDENT / DEMO-2026',author:null,destination:'https://scholarship.example/upload',crossOrigin:false,findings:[],signed:false},
  signed: {label:'Signed document',name:'signed-certificate.pdf',kind:'Signed academic certificate',size:'248 KB',title:'Academic certificate',subtitle:'Fictional signed-document sample',number:'CERTIFICATE / DEMO-014',author:'Sample Institution',destination:'https://files.scholarship-storage.example/upload',crossOrigin:true,findings:[{id:'signature',label:'Digital-signature indicator',value:'Indicator only · validity not checked',kind:'Authentication indicator',why:'Changing a signed document may invalidate its signature. Modification is unavailable in this scenario.',action:null},{id:'qr',label:'QR-code indicator',value:'Detected in this sample scenario',kind:'Authentication indicator',why:'A QR code can contain additional information. Detecting it does not verify or remove what it encodes.',action:null}],signed:true}
};
export const initialState = (scenario='identity') => ({scenario,phase:'choose',selected:[],changeConsent:false,uploadConsent:false,output:null,view:'original',observed:null,agentStep:0,originalAcknowledged:false});
export const canProtect = s => s.phase==='review' && !SCENARIOS[s.scenario].signed && s.selected.length>0 && s.changeConsent;
export const canSubmit = s => s.phase==='ready' && s.uploadConsent && (s.output==='protected' || s.originalAcknowledged);
export function transition(s,action){
  const scenario=SCENARIOS[s.scenario];
  switch(action.type){
    case 'scenario': return SCENARIOS[action.value] ? initialState(action.value) : s;
    case 'reset': return initialState(s.scenario);
    case 'choose': return s.phase==='choose' ? {...s,phase:'selected'} : s;
    case 'inspect': return s.phase==='selected' ? {...s,phase:'inspecting',agentStep:0} : s;
    case 'agent': return s.phase==='inspecting' ? {...s,agentStep:action.value} : s;
    case 'inspected': return s.phase==='inspecting' ? {...s,phase:'review'} : s;
    case 'toggle': {
      if(s.phase!=='review'||scenario.signed||!scenario.findings.some(f=>f.id===action.value&&f.action))return s;
      const selected=s.selected.includes(action.value)?s.selected.filter(id=>id!==action.value):[...s.selected,action.value];
      return {...s,selected,changeConsent:false,uploadConsent:false,output:null,originalAcknowledged:false};
    }
    case 'changeConsent': return s.phase==='review'&&s.selected.length&&!scenario.signed ? {...s,changeConsent:action.value===true} : s;
    case 'protect': return canProtect(s) ? {...s,phase:'protecting',uploadConsent:false} : s;
    case 'verified': return s.phase==='protecting' ? {...s,phase:'ready',output:'protected',view:'protected',uploadConsent:false} : s;
    case 'original': return s.phase==='review' ? {...s,phase:'ready',output:'original',view:'original',uploadConsent:false,originalAcknowledged:true} : s;
    case 'review': return s.phase==='ready' ? {...s,phase:'review',output:null,view:'original',changeConsent:false,uploadConsent:false,originalAcknowledged:false} : s;
    case 'view': return s.output==='protected'&&['original','protected'].includes(action.value) ? {...s,view:action.value} : s;
    case 'uploadConsent': return s.phase==='ready' ? {...s,uploadConsent:action.value===true} : s;
    case 'submit': return canSubmit(s) ? {...s,phase:'submitted',observed:scenario.destination} : s;
    default: return s;
  }
}

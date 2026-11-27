import test from 'node:test';
import assert from 'node:assert/strict';
import {initialState,transition,canProtect,canSubmit} from './dist/model.mjs';
const review=scenario=>['choose','inspect','inspected'].reduce((s,type)=>transition(s,{type}),initialState(scenario));
test('changes and submission require separate explicit approval',()=>{
 let s=review('identity');
 assert.equal(canProtect(s),false);assert.equal(transition(s,{type:'protect'}),s);
 s=transition(s,{type:'toggle',value:'aadhaar'});assert.equal(canProtect(s),false);
 s=transition(s,{type:'changeConsent',value:true});assert.equal(canProtect(s),true);
 s=transition(s,{type:'protect'});assert.equal(s.observed,null);assert.equal(canSubmit(s),false);
 s=transition(s,{type:'verified'});assert.equal(s.view,'protected');assert.equal(s.uploadConsent,false);assert.equal(canSubmit(s),false);
 assert.equal(transition(s,{type:'submit'}),s);
 s=transition(s,{type:'uploadConsent',value:true});assert.equal(canSubmit(s),true);
 s=transition(s,{type:'submit'});assert.equal(s.phase,'submitted');assert.ok(s.observed.startsWith('https://'));
});
test('changing selected actions revokes modification consent',()=>{
 let s=review('identity');
 s=transition(s,{type:'toggle',value:'aadhaar'});s=transition(s,{type:'changeConsent',value:true});
 s=transition(s,{type:'toggle',value:'author'});assert.equal(s.changeConsent,false);assert.equal(canProtect(s),false);
});
test('signed scenario cannot be modified and original still needs upload consent',()=>{
 let s=review('signed');
 s=transition(s,{type:'toggle',value:'signature'});s=transition(s,{type:'changeConsent',value:true});assert.equal(canProtect(s),false);
 assert.equal(transition(s,{type:'protect'}),s);s=transition(s,{type:'original'});assert.equal(s.output,'original');assert.equal(canSubmit(s),false);
 s=transition(s,{type:'uploadConsent',value:true});assert.equal(canSubmit(s),true);
});
test('clean sample can proceed unchanged without modification',()=>{
 let s=review('clean');assert.equal(canProtect(s),false);s=transition(s,{type:'original'});assert.equal(s.output,'original');assert.equal(s.observed,null);
 s=transition(s,{type:'uploadConsent',value:true});s=transition(s,{type:'submit'});assert.equal(s.observed,'https://scholarship.example/upload');
});
test('switching scenarios resets consent, previews and destination observations',()=>{
 let s=review('identity');s=transition(s,{type:'original'});s=transition(s,{type:'uploadConsent',value:true});s=transition(s,{type:'submit'});
 s=transition(s,{type:'scenario',value:'signed'});assert.deepEqual(s,initialState('signed'));
});
test('returning to findings revokes submission consent and protected output',()=>{
 let s=review('identity');s=transition(s,{type:'original'});s=transition(s,{type:'uploadConsent',value:true});s=transition(s,{type:'review'});
 assert.equal(s.phase,'review');assert.equal(s.uploadConsent,false);assert.equal(s.output,null);assert.equal(canSubmit(s),false);
});

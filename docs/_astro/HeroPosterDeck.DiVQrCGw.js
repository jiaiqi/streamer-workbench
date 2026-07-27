import{r as c}from"./index.CVf8TyFT.js";var h={exports:{}},u={};/**
 * @license React
 * react-jsx-runtime.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var b=c,y=Symbol.for("react.element"),k=Symbol.for("react.fragment"),w=Object.prototype.hasOwnProperty,E=b.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner,_={key:!0,ref:!0,__self:!0,__source:!0};function m(a,t,f){var r,l={},x=null,p=null;f!==void 0&&(x=""+f),t.key!==void 0&&(x=""+t.key),t.ref!==void 0&&(p=t.ref);for(r in t)w.call(t,r)&&!_.hasOwnProperty(r)&&(l[r]=t[r]);if(a&&a.defaultProps)for(r in t=a.defaultProps,t)l[r]===void 0&&(l[r]=t[r]);return{$$typeof:y,type:a,key:x,ref:p,props:l,_owner:E.current}}u.Fragment=k;u.jsx=m;u.jsxs=m;h.exports=u;var s=h.exports;const i=[{id:"ocean",name:"海洋柔光",c1:"#2b544e",c2:"#246e60",c3:"#bce0d2"},{id:"dream",name:"梦幻海洋",c1:"#5f4658",c2:"#7c4a63",c3:"#f0d0e0"},{id:"cream",name:"奶油花园",c1:"#6b4a3f",c2:"#8a4a38",c3:"#f7c7b2"},{id:"green",name:"青提气泡",c1:"#3d5e58",c2:"#4f8576",c3:"#d4e8b8"},{id:"note",name:"卡通音符",c1:"#465044",c2:"#406e5a",c3:"#c6e9d2"},{id:"glass",name:"奶油玻璃",c1:"#465064",c2:"#406a94",c3:"#e4eef6"},{id:"retro",name:"轻复古唱片",c1:"#3a2820",c2:"#7a4a32",c3:"#e8b888"}];function N(){const[a,t]=c.useState(0),[f,r]=c.useState(1),[l,x]=c.useState({x:50,y:50}),p=c.useRef(null);return c.useEffect(()=>{const o=setInterval(()=>t(e=>(e+1)%i.length),3e3);return()=>clearInterval(o)},[]),c.useEffect(()=>{const o=e=>{const n=e.target?.tagName;n==="INPUT"||n==="TEXTAREA"||(e.key==="ArrowLeft"&&t(d=>(d-1+i.length)%i.length),e.key==="ArrowRight"&&t(d=>(d+1)%i.length),e.key==="ArrowUp"&&r(1),e.key==="ArrowDown"&&r(2))};return window.addEventListener("keydown",o),()=>window.removeEventListener("keydown",o)},[]),c.useEffect(()=>{const o=n=>{if(!p.current)return;const d=p.current.getBoundingClientRect(),g=(n.clientX-d.left)/d.width*100,v=(n.clientY-d.top)/d.height*100;x({x:g,y:v})},e=p.current;if(e)return e.addEventListener("mousemove",o),()=>e.removeEventListener("mousemove",o)},[]),c.useEffect(()=>{const o=i[a];document.documentElement.style.setProperty("--active-theme-c2",o.c2)},[a]),s.jsxs("div",{ref:p,className:"hero-deck",children:[s.jsx("div",{className:"hero-spotlight",style:{background:`radial-gradient(circle, ${i[a].c2}55, transparent 65%)`,left:`${l.x}%`,top:`${l.y}%`}}),s.jsx("div",{className:"poster-stack",children:[0,1,2,3].map(o=>{const e=(a+o)%i.length,n=i[e];return s.jsx("div",{className:"poster-card",style:{background:`linear-gradient(180deg, ${n.c1} 0%, ${n.c2} 30%, ${n.c3} 65%, #f7f6f2 100%)`,color:"#fff",textShadow:"0 1px 4px rgba(0,0,0,.3)"},children:n.name},o)})}),s.jsx("div",{className:"poster-dots",children:i.map((o,e)=>s.jsx("span",{className:e===a?"active":""},e))}),s.jsxs("div",{className:"page-indicator",children:[s.jsx("button",{className:f===1?"active":"",onClick:()=>r(1),children:"P1"}),s.jsx("button",{className:f===2?"active":"",onClick:()=>r(2),children:"P2"})]}),s.jsx("style",{children:`
        .hero-deck {
          position: relative;
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 500px;
        }
        .hero-spotlight {
          position: absolute;
          width: 380px;
          height: 380px;
          border-radius: 50%;
          filter: blur(60px);
          transform: translate(-50%, -50%);
          transition: background 0.6s var(--ease-cinematic);
          pointer-events: none;
        }
        .poster-stack {
          position: relative;
          width: 280px;
          height: 497px;
        }
        .poster-card {
          position: absolute;
          width: 260px;
          height: 462px;
          border-radius: var(--radius-lg);
          overflow: hidden;
          background: var(--surface-1);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-card);
          display: grid;
          place-items: center;
          font-size: 14px;
          transition: all 0.5s var(--ease-cinematic);
          cursor: pointer;
        }
        .poster-card:nth-child(1) { z-index: 4; top: 0; left: 10px; transform: rotate(-2deg); }
        .poster-card:nth-child(2) { z-index: 3; top: 14px; left: -28px; transform: rotate(-6deg); }
        .poster-card:nth-child(3) { z-index: 2; top: 10px; left: 44px; transform: rotate(3deg); }
        .poster-card:nth-child(4) { z-index: 1; top: 26px; left: 8px; transform: rotate(7deg); }
        .poster-stack:hover .poster-card:nth-child(1) { transform: rotate(-4deg) translateX(-60px); }
        .poster-stack:hover .poster-card:nth-child(2) { transform: rotate(-14deg) translateX(-100px); }
        .poster-stack:hover .poster-card:nth-child(3) { transform: rotate(8deg) translateX(80px); }
        .poster-stack:hover .poster-card:nth-child(4) { transform: rotate(16deg) translateX(40px); }
        .poster-dots {
          position: absolute;
          bottom: -36px;
          left: 50%;
          transform: translateX(-50%);
          display: flex;
          gap: 8px;
        }
        .poster-dots span {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--text-3);
          transition: all 0.3s;
        }
        .poster-dots span.active {
          background: var(--spotlight);
          box-shadow: var(--glow-spot);
        }
        .page-indicator {
          position: absolute;
          top: 16px;
          right: -8px;
          display: flex;
          flex-direction: column;
          gap: 4px;
          font-family: var(--font-mono);
        }
        .page-indicator button {
          width: 36px;
          height: 28px;
          border-radius: 6px;
          border: 1px solid var(--border);
          background: var(--surface-1);
          color: var(--text-3);
          font-size: 11px;
          cursor: pointer;
          transition: all 0.2s;
        }
        .page-indicator button.active {
          background: var(--primary);
          color: var(--primary-foreground);
          border-color: var(--primary);
        }
      `})]})}export{N as default};

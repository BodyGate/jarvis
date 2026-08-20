// Motore 3D di JARVIS — nucleo deformante via shader + corpi orbitanti per
// conversazione. Porting da vanilla-adattamento del design handoff
// (design_handoff_jarvis_interface/JARVIS v2.dc.html): gli shader GLSL, la
// tabella STATES e la matematica di orbita/volo camera sono trasferiti
// pressoché identici, come richiesto dal documento di handoff — cambia solo
// l'involucro (niente React/DCLogic, dati reali invece dei placeholder).
import * as THREE from "./vendor/three.module.js";

const NOISE = `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 perm(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g;
  vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=perm(perm(perm(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`;

const FIELD = `
uniform float uTime,uAmp,uFreq,uSpeed,uRipple,uPulse,uSwirl,uTurb;
vec3 deform(vec3 dir,out float d){
  float t=uTime*uSpeed;
  vec3 q=dir;
  float sw=uSwirl*0.9;
  float ca=cos(dir.y*sw+t*0.5),sa=sin(dir.y*sw+t*0.5);
  q.xz=mat2(ca,-sa,sa,ca)*q.xz;
  float n1=snoise(q*uFreq+vec3(0.0,t*0.55,t*0.31));
  float n2=snoise(q*uFreq*2.35+vec3(t*0.8,0.0,-t*0.44))*0.46;
  float n3=snoise(q*uFreq*5.1+vec3(-t*1.3,t*0.9,0.0))*0.19;
  float lobes=pow(abs(snoise(q*0.95+vec3(0.0,t*0.22,0.0))),1.6)*0.5;
  float ripple=sin(dir.y*11.0-t*4.2)*cos(dir.x*7.0+t*1.7)*uRipple;
  d=((n1+n2+n3)*uTurb+lobes)*uAmp+ripple+sin(t*1.55)*uPulse;
  return dir*(1.0+d);
}`;

export const STATES = {
  idle: { amp: 0.115, freq: 1.55, speed: 0.34, ripple: 0.0, pulse: 0.03, swirl: 0.55, spread: 0.13, density: 0.5, size: 1.0, glow: 0.85, mixA: 0.0 },
  listening: { amp: 0.2, freq: 2.05, speed: 0.85, ripple: 0.03, pulse: 0.07, swirl: 1.1, spread: 0.34, density: 0.92, size: 1.12, glow: 1.35, mixA: 0.45 },
  processing: { amp: 0.3, freq: 3.1, speed: 1.45, ripple: 0.01, pulse: 0.014, swirl: 1.85, spread: 0.17, density: 1.0, size: 0.82, glow: 1.1, mixA: 1.0 },
  responding: { amp: 0.15, freq: 1.25, speed: 0.62, ripple: 0.006, pulse: 0.115, swirl: 0.35, spread: 0.46, density: 0.78, size: 1.22, glow: 1.55, mixA: 0.2 },
};

export const BRAINS = [
  { name: "Groq", color: "#4ff0d6", note: "fast path" },
  { name: "Gemini", color: "#8b7cff", note: "long context" },
  { name: "Claude", color: "#ff9d6b", note: "reasoning" },
  // Quarto "cervello" non presente nel design originale: il nostro router
  // reale delega anche a ChatGPT (ADR-0003), non solo a Claude.
  { name: "ChatGPT", color: "#19c37d", note: "creativity" },
];

function glowTex() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const ctx = c.getContext("2d");
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.25, "rgba(255,255,255,.42)");
  g.addColorStop(0.6, "rgba(255,255,255,.09)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

export class Scene3D {
  constructor(canvas, labelLayer, { accentA = "#2b6bff", accentB = "#a15cff", nebula = true, turbulence = 1, coreScale = 1, particleDensity = 1, leftBound = 292 } = {}) {
    this.canvas = canvas;
    this.labelLayer = labelLayer;
    this.mobile = window.innerWidth < 900 || /Mobi|Android/i.test(navigator.userAgent);
    this.opts = { accentA, accentB, nebula, turbulence, coreScale, particleDensity };
    this.leftBound = this.mobile ? 14 : leftBound;
    this.bodies = [];
    this.bodyObjs = [];
    this.labelEls = [];
    this.selected = null;
    this.hoverObj = null;
    this.pickPending = false;
    this.onNucleusClick = null;
    this.onBodyClick = null;
  }

  async init() {
    const canvas = this.canvas;
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: !this.mobile, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.mobile ? 2 : 1.85));
    renderer.setClearColor(0x04050b, 1);
    this.renderer = renderer;

    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x05070f, 0.008);
    const camera = new THREE.PerspectiveCamera(52, 1, 0.1, 500);
    this.scene = scene;
    this.camera = camera;

    this.accentA = new THREE.Color(this.opts.accentA);
    this.accentB = new THREE.Color(this.opts.accentB);
    this.center = new THREE.Vector3(this.mobile ? 0 : 2.4, 0, 0);
    camera.position.set(this.center.x, 1.4, 27);

    this._buildNebula();
    this._buildStars();
    this._buildNucleus();

    this.cur = { ...STATES.idle };
    this.tgt = { ...STATES.idle };
    this.home = new THREE.Vector3(this.center.x, 1.4, 27);
    this.camPos = camera.position.clone();
    this.camLook = this.center.clone();
    this.pointer = new THREE.Vector2(0, 0);
    this.parallax = new THREE.Vector2(0, 0);
    this.ray = new THREE.Raycaster();
    this.ndc = new THREE.Vector2(-2, -2);

    this._onResize = () => {
      const w = canvas.clientWidth || window.innerWidth;
      const h = canvas.clientHeight || window.innerHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      this.dpi = { w, h };
    };
    this._onResize();
    window.addEventListener("resize", this._onResize);

    this._onEsc = (e) => {
      if (e.key === "Escape") this.deselect();
    };
    window.addEventListener("keydown", this._onEsc);

    canvas.addEventListener("pointermove", (e) => {
      const r = canvas.getBoundingClientRect();
      this.ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      this.pointer.copy(this.ndc);
      this.pickPending = true;
    });
    canvas.addEventListener("pointerdown", (e) => {
      const r = canvas.getBoundingClientRect();
      this.ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      this._handleClick();
    });

    this.clock = new THREE.Clock();
    this.last = 0;
    this._loop();
  }

  destroy() {
    cancelAnimationFrame(this.raf);
    window.removeEventListener("resize", this._onResize);
    window.removeEventListener("keydown", this._onEsc);
    if (this.renderer) this.renderer.dispose();
  }

  // ---------- Sfondo ----------

  _buildNebula() {
    const mat = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      depthWrite: false,
      uniforms: { uTime: { value: 0 }, uA: { value: this.accentA }, uB: { value: this.accentB }, uOn: { value: this.opts.nebula ? 1 : 0 } },
      vertexShader: `varying vec3 vP; void main(){ vP=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
      fragmentShader:
        NOISE +
        `
        uniform float uTime,uOn; uniform vec3 uA,uB; varying vec3 vP;
        float ridged(vec3 p){ return 1.0-abs(snoise(p)); }
        void main(){
          vec3 d=normalize(vP); float t=uTime*0.008;
          vec3 warp=vec3(snoise(d*1.3+t),snoise(d*1.3+7.0-t),snoise(d*1.3+13.0));
          vec3 q=d*2.2+warp*0.55;
          float f=0.0,a=0.5;
          for(int i=0;i<5;i++){ f+=a*ridged(q); q*=2.07; a*=0.5; }
          float fil=pow(clamp(f-0.62,0.0,1.0),1.7)*2.3;
          float dust=smoothstep(0.55,1.0,f)*0.35;
          float lane=smoothstep(0.5,0.0,abs(d.y*1.9+d.x*0.35+0.05));
          vec3 col=mix(uA*0.30,uB*0.55,clamp(fil*0.8,0.0,1.0));
          col+=vec3(0.10,0.30,0.62)*fil*0.55;
          col+=uB*dust*0.35;
          col*=0.20+lane*1.05;
          col+=vec3(0.015,0.02,0.045);
          gl_FragColor=vec4(col*uOn,1.0);
        }`,
    });
    this.nebulaMat = mat;
    this.scene.add(new THREE.Mesh(new THREE.SphereGeometry(210, 40, 28), mat));
  }

  _buildStars() {
    this.starLayers = [];
    const tex = glowTex();
    const layers = this.mobile
      ? [
          [900, 60, 2.6],
          [520, 115, 3.8],
        ]
      : [
          [2200, 55, 2.6],
          [1500, 105, 3.6],
          [900, 160, 5.2],
        ];
    layers.forEach(([n, rad, size], li) => {
      const pos = new Float32Array(n * 3);
      const col = new Float32Array(n * 3);
      const c = new THREE.Color();
      for (let i = 0; i < n; i++) {
        const v = new THREE.Vector3().randomDirection().multiplyScalar(rad * (0.7 + Math.random() * 0.6));
        pos.set([v.x, v.y, v.z], i * 3);
        c.copy(Math.random() < 0.5 ? this.accentA : this.accentB).lerp(new THREE.Color(0xffffff), 0.35 + Math.random() * 0.55);
        col.set([c.r, c.g, c.b], i * 3);
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      g.setAttribute("color", new THREE.BufferAttribute(col, 3));
      const m = new THREE.PointsMaterial({ size, map: tex, vertexColors: true, transparent: true, opacity: 0.5 - li * 0.07, blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true });
      const p = new THREE.Points(g, m);
      this.scene.add(p);
      this.starLayers.push({ p, k: 0.02 + li * 0.035 });
    });
  }

  // ---------- Nucleo ----------

  _buildNucleus() {
    const group = new THREE.Group();
    group.position.copy(this.center);
    this.nucleus = group;
    this.scene.add(group);

    const uni = {
      uTime: { value: 0 }, uAmp: { value: 0.115 }, uFreq: { value: 1.55 }, uSpeed: { value: 0.34 },
      uRipple: { value: 0 }, uPulse: { value: 0.03 }, uSwirl: { value: 0.55 }, uTurb: { value: this.opts.turbulence },
      uRadius: { value: 3.5 * this.opts.coreScale }, uGlow: { value: 0.85 }, uMix: { value: 0 },
      uA: { value: this.accentA }, uB: { value: this.accentB },
    };
    this.nu = uni;

    const vert =
      NOISE +
      FIELD +
      `
      uniform float uRadius; varying float vD; varying vec3 vN; varying vec3 vV;
      void main(){
        vec3 dir=normalize(position); float d;
        vec3 np=deform(dir,d)*uRadius; vD=d;
        float e=0.035;
        vec3 t1=normalize(cross(dir,vec3(0.0,1.0,0.0))+vec3(0.0001));
        vec3 t2=normalize(cross(dir,t1));
        float da,db;
        vec3 pa=deform(normalize(dir+t1*e),da)*uRadius;
        vec3 pb=deform(normalize(dir+t2*e),db)*uRadius;
        vec3 n=normalize(cross(pa-np,pb-np));
        if(dot(n,dir)<0.0) n=-n;
        vec4 mv=modelViewMatrix*vec4(np,1.0);
        vN=normalize(normalMatrix*n); vV=normalize(-mv.xyz);
        gl_Position=projectionMatrix*mv;
      }`;

    group.add(
      new THREE.Mesh(
        new THREE.IcosahedronGeometry(1, this.mobile ? 5 : 7),
        new THREE.ShaderMaterial({
          uniforms: uni, vertexShader: vert, transparent: true, depthWrite: false,
          fragmentShader: `
            uniform vec3 uA,uB; uniform float uGlow,uMix;
            varying float vD; varying vec3 vN; varying vec3 vV;
            void main(){
              float fres=1.0-abs(dot(normalize(vN),normalize(vV)));
              float rim=pow(clamp(fres,0.0,1.0),2.3);
              vec3 base=mix(uA,uB,clamp(vD*1.9+0.5,0.0,1.0));
              base=mix(base,vec3(0.55,0.92,1.0),uMix*0.45);
              vec3 c=base*(0.16+rim*2.1*uGlow);
              c+=vec3(0.30,0.55,1.0)*pow(rim,5.0)*uGlow*0.9;
              gl_FragColor=vec4(c,0.30+rim*0.62);
            }`,
        })
      )
    );

    group.add(
      new THREE.Mesh(
        new THREE.IcosahedronGeometry(1.028, this.mobile ? 2 : 3),
        new THREE.ShaderMaterial({
          uniforms: uni, vertexShader: vert, wireframe: true, transparent: true,
          depthWrite: false, blending: THREE.AdditiveBlending,
          fragmentShader: `
            uniform vec3 uA,uB; uniform float uGlow,uMix; varying float vD; varying vec3 vN; varying vec3 vV;
            void main(){
              float fres=1.0-abs(dot(normalize(vN),normalize(vV)));
              vec3 c=mix(uA,uB,clamp(vD*2.0+0.5,0.0,1.0));
              c=mix(c,vec3(0.6,0.95,1.0),uMix*0.5);
              gl_FragColor=vec4(c*(0.5+fres*1.4)*uGlow,0.16+fres*0.22);
            }`,
        })
      )
    );

    const inner = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1, 3),
      new THREE.ShaderMaterial({
        uniforms: uni, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
        vertexShader:
          NOISE +
          FIELD +
          `
          uniform float uRadius; varying vec3 vN; varying vec3 vV;
          void main(){
            vec3 dir=normalize(position); float d;
            vec3 np=deform(dir,d)*uRadius*0.44;
            vec4 mv=modelViewMatrix*vec4(np,1.0);
            vN=normalize(normalMatrix*dir); vV=normalize(-mv.xyz);
            gl_Position=projectionMatrix*mv;
          }`,
        fragmentShader: `
          uniform vec3 uA,uB; uniform float uGlow,uMix; varying vec3 vN; varying vec3 vV;
          void main(){
            float f=1.0-abs(dot(normalize(vN),normalize(vV)));
            vec3 c=mix(vec3(0.72,0.88,1.0),uB,uMix*0.5);
            gl_FragColor=vec4(c*(0.30+pow(f,1.6)*1.5)*uGlow,0.42);
          }`,
      })
    );
    group.add(inner);

    const N = this.mobile ? 3200 : 11000;
    this.shellCount = N;
    const dir = new Float32Array(N * 3);
    const seed = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      const v = new THREE.Vector3().randomDirection();
      dir.set([v.x, v.y, v.z], i * 3);
      seed[i] = Math.random();
    }
    const sg = new THREE.BufferGeometry();
    sg.setAttribute("position", new THREE.BufferAttribute(dir, 3));
    sg.setAttribute("aSeed", new THREE.BufferAttribute(seed, 1));
    this.shellGeo = sg;
    this.shellUni = Object.assign({}, uni, { uSpread: { value: 0.13 }, uPointSize: { value: this.mobile ? 2.6 : 2.1 }, uDpr: { value: this.renderer.getPixelRatio() } });
    group.add(
      new THREE.Points(
        sg,
        new THREE.ShaderMaterial({
          uniforms: this.shellUni, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
          vertexShader:
            NOISE +
            FIELD +
            `
            uniform float uRadius,uSpread,uPointSize,uDpr; attribute float aSeed;
            varying float vD; varying float vS;
            void main(){
              vec3 dir=normalize(position); float d;
              vec3 np=deform(dir,d);
              float t=uTime*uSpeed;
              float wob=snoise(dir*4.0+vec3(aSeed*12.0,t*0.9,0.0));
              float shellR=1.0+uSpread*(0.35+aSeed*1.35)+wob*uSpread*0.55;
              vec3 p=np*shellR*uRadius;
              vD=d; vS=aSeed;
              vec4 mv=modelViewMatrix*vec4(p,1.0);
              gl_PointSize=uPointSize*uDpr*(0.45+aSeed)*(90.0/max(-mv.z,1.0));
              gl_Position=projectionMatrix*mv;
            }`,
          fragmentShader: `
            uniform vec3 uA,uB; uniform float uGlow,uMix; varying float vD; varying float vS;
            void main(){
              vec2 uv=gl_PointCoord-0.5; float r=length(uv);
              if(r>0.5) discard;
              float a=smoothstep(0.5,0.0,r);
              vec3 c=mix(uA,uB,clamp(vD*2.0+vS*0.6,0.0,1.0));
              c=mix(c,vec3(0.65,0.95,1.0),uMix*0.6);
              gl_FragColor=vec4(c*(1.1+uGlow*0.7),a*a*(0.30+uGlow*0.32));
            }`,
        })
      )
    );

    const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex(), color: 0x6aa8ff, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending, depthWrite: false }));
    halo.scale.setScalar(26);
    this.halo = halo;
    group.add(halo);

    const hit = new THREE.Mesh(new THREE.SphereGeometry(5.2, 16, 12), new THREE.MeshBasicMaterial({ visible: false }));
    hit.userData.nucleus = true;
    this.nucleusHit = hit;
    group.add(hit);
  }

  // ---------- Corpi orbitanti ----------

  _orbitPoint(o, angle, v) {
    v.set(
      Math.cos(angle) * o.radius + this.center.x,
      Math.sin(angle + o.incl) * o.radius * 0.26 + o.yOff,
      Math.sin(angle) * o.radius * 0.72 + o.depth
    );
    return v;
  }

  /** `list`: array di Body (vedi app.js per la forma). Rimpiazza i corpi esistenti. */
  setBodies(list) {
    this._clearBodies();
    this.bodies = this.mobile ? list.slice(0, 5) : list;
    const tex = glowTex();
    this.bodies.forEach((b, i) => {
      const g = new THREE.Group();
      const r = 0.34 + b.rel * 0.95;
      const brainDef = BRAINS.find((x) => x.name === b.brain) || BRAINS[0];
      const col = new THREE.Color(brainDef.color).lerp(this.accentA, 0.35 - b.rel * 0.25);

      const core = new THREE.Mesh(new THREE.IcosahedronGeometry(r, 1), new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.35 + b.rel * 0.5 }));
      g.add(core);
      const wire = new THREE.Mesh(new THREE.IcosahedronGeometry(r * 1.22, 1), new THREE.MeshBasicMaterial({ color: col, wireframe: true, transparent: true, opacity: 0.16 + b.rel * 0.3, blending: THREE.AdditiveBlending, depthWrite: false }));
      g.add(wire);
      const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, color: col, transparent: true, opacity: 0.24 + b.rel * 0.42, blending: THREE.AdditiveBlending, depthWrite: false }));
      glow.scale.setScalar(r * (7 + b.rel * 5));
      g.add(glow);
      const hit = new THREE.Mesh(new THREE.SphereGeometry(Math.max(r * 2.4, 1.5), 12, 8), new THREE.MeshBasicMaterial({ visible: false }));
      hit.userData.bodyId = b.id;
      g.add(hit);

      const o = {
        g, core, wire, glow, hit, data: b,
        radius: 8.5 + i * (this.mobile ? 3.4 : 2.05) + (1 - b.rel) * 4.5,
        angle: (i * 2.399) % (Math.PI * 2),
        speed: (0.055 + b.rel * 0.07) * (i % 2 ? -1 : 1),
        incl: (Math.random() - 0.5) * 0.85,
        yOff: (Math.random() - 0.5) * 7,
        depth: -6 - Math.random() * 14 - i * 1.2,
        baseR: r, pulse: Math.random() * 6.28, col,
      };

      const pts = [];
      const v = new THREE.Vector3();
      for (let s = 0; s <= 160; s++) pts.push(this._orbitPoint(o, (s / 160) * Math.PI * 2, v).clone());
      const lg = new THREE.BufferGeometry().setFromPoints(pts);
      const line = new THREE.Line(lg, new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.05 + b.rel * 0.09, blending: THREE.AdditiveBlending, depthWrite: false }));
      o.line = line;
      this.scene.add(line);
      this.bodyObjs.push(o);
      this.scene.add(g);

      const el = document.createElement("div");
      el.className = "jv-label";
      el.innerHTML = `<span class="jv-label-tick" style="background:${brainDef.color};box-shadow:0 0 7px 1px ${brainDef.color}88;"></span>
        <span class="jv-label-text"><span class="jv-label-name">${escapeHtml(b.name)}</span><span class="jv-label-meta">${escapeHtml((b.kind === "project" ? "Project" : "Chat") + " · " + b.when)}</span></span>`;
      this.labelLayer.appendChild(el);
      this.labelEls.push(el);
    });
  }

  _clearBodies() {
    for (const o of this.bodyObjs) {
      this.scene.remove(o.g);
      this.scene.remove(o.line);
    }
    this.bodyObjs = [];
    for (const el of this.labelEls) el.remove();
    this.labelEls = [];
    this.selected = null;
    this.hoverObj = null;
  }

  // ---------- Stato / interazione ----------

  setMode(mode) {
    this.tgt = { ...STATES[mode] };
  }

  select(id) {
    const o = this.bodyObjs.find((x) => x.data.id === id);
    if (!o) return;
    this.selected = o;
    if (this.onSelectionChange) this.onSelectionChange(o.data);
  }

  deselect() {
    this.selected = null;
    if (this.onSelectionChange) this.onSelectionChange(null);
  }

  hoverRow(id) {
    this.hoverObj = this.bodyObjs.find((x) => x.data.id === id) || null;
  }

  clearHover() {
    this.hoverObj = null;
  }

  _handleClick() {
    if (!this.camera) return;
    this.ray.setFromCamera(this.ndc, this.camera);
    const hits = this.ray.intersectObjects([this.nucleusHit, ...this.bodyObjs.map((o) => o.hit)], false);
    if (!hits.length) return;
    const u = hits[0].object.userData;
    if (u.nucleus) {
      if (this.onNucleusClick) this.onNucleusClick();
      return;
    }
    if (u.bodyId != null) {
      if (this.selected && this.selected.data.id === u.bodyId) this.deselect();
      else this.select(u.bodyId);
      if (this.onBodyClick) this.onBodyClick(u.bodyId);
    }
  }

  // ---------- Loop ----------

  _loop = () => {
    this.raf = requestAnimationFrame(this._loop);
    const t = this.clock.getElapsedTime();
    const dt = this.last ? Math.min(Math.max(t - this.last, 0.0005), 0.05) : 0.016;
    this.last = t;

    const k = 1 - Math.exp(-dt * 2.6);
    const turb = this.opts.turbulence;
    const dens = this.opts.particleDensity;
    for (const key in this.tgt) this.cur[key] += (this.tgt[key] - this.cur[key]) * k;

    const u = this.nu;
    u.uTime.value = t;
    u.uAmp.value = this.cur.amp;
    u.uFreq.value = this.cur.freq;
    u.uSpeed.value = this.cur.speed;
    u.uRipple.value = this.cur.ripple;
    u.uPulse.value = this.cur.pulse;
    u.uSwirl.value = this.cur.swirl;
    u.uTurb.value = turb;
    u.uGlow.value = this.cur.glow;
    u.uMix.value = this.cur.mixA;
    u.uRadius.value = 3.5 * this.opts.coreScale * (0.92 + this.cur.size * 0.08);
    this.shellUni.uSpread.value = this.cur.spread;
    this.shellGeo.setDrawRange(0, Math.floor(this.shellCount * Math.min(this.cur.density * dens, 1)));
    this.halo.material.opacity = 0.28 + this.cur.glow * 0.28;
    this.halo.scale.setScalar(24 + this.cur.glow * 7);
    this.nucleus.rotation.y += dt * (0.05 + this.cur.speed * 0.05);
    this.nucleus.rotation.x = Math.sin(t * 0.12) * 0.09;
    if (this.nebulaMat) {
      this.nebulaMat.uniforms.uTime.value = t;
      this.nebulaMat.uniforms.uOn.value = this.opts.nebula ? 1 : 0;
    }

    const tmp = new THREE.Vector3();
    for (const o of this.bodyObjs) {
      o.angle += dt * o.speed;
      o.g.position.copy(this._orbitPoint(o, o.angle, tmp));
      const isSel = this.selected === o;
      const isHov = this.hoverObj === o;
      const s = (1 + Math.sin(t * 0.9 + o.pulse) * 0.05) * (isSel ? 1.35 : isHov ? 1.16 : 1);
      o.g.scale.setScalar(s);
      o.wire.rotation.y += dt * 0.35;
      o.wire.rotation.x -= dt * 0.18;
      o.glow.material.opacity = (0.24 + o.data.rel * 0.42) * (isSel ? 1.6 : isHov ? 1.3 : 1);
      o.line.material.opacity = (0.05 + o.data.rel * 0.09) * (isSel || isHov ? 3.2 : 1);
    }

    if (this.pickPending) {
      this.pickPending = false;
      this.ray.setFromCamera(this.pointer, this.camera);
      const hits = this.ray.intersectObjects([this.nucleusHit, ...this.bodyObjs.map((o) => o.hit)], false);
      const hitObj = hits.length ? hits[0].object : null;
      this.hoverObj = hitObj && hitObj.userData.bodyId != null ? this.bodyObjs.find((o) => o.data.id === hitObj.userData.bodyId) : null;
      this.renderer.domElement.style.cursor = hitObj ? "pointer" : "default";
    }

    const want = new THREE.Vector3();
    const look = new THREE.Vector3();
    if (this.selected) {
      const p = this.selected.g.position;
      look.copy(p);
      const off = p.clone().sub(this.center).normalize().multiplyScalar(this.selected.baseR * 6 + 4.2);
      want.copy(p).add(new THREE.Vector3(off.x * 0.4, off.y * 0.4 + 1.4, Math.abs(off.z) + 7.5));
    } else {
      want.copy(this.home);
      look.copy(this.center);
    }
    const ck = 1 - Math.exp(-dt * (this.selected ? 2.2 : 1.5));
    this.camPos.lerp(want, ck);
    this.camLook.lerp(look, ck);

    this.parallax.x += (this.pointer.x * (this.mobile ? 1.3 : 2.3) - this.parallax.x) * (1 - Math.exp(-dt * 2.2));
    this.parallax.y += (this.pointer.y * (this.mobile ? 0.8 : 1.5) - this.parallax.y) * (1 - Math.exp(-dt * 2.2));
    this.camera.position.set(this.camPos.x + this.parallax.x, this.camPos.y + this.parallax.y, this.camPos.z);
    this.camera.lookAt(this.camLook);

    for (const s of this.starLayers) {
      s.p.rotation.y = t * s.k * 0.05;
      s.p.position.x = -this.parallax.x * s.k * 8;
      s.p.position.y = -this.parallax.y * s.k * 8;
    }

    this._placeLabels();
    this.renderer.render(this.scene, this.camera);
  };

  _placeLabels() {
    const w = this.dpi ? this.dpi.w : window.innerWidth;
    const h = this.dpi ? this.dpi.h : window.innerHeight;
    const leftBound = this.leftBound;
    const order = this.bodyObjs.map((o, i) => ({ o, i })).sort((a, b) => b.o.data.rel - a.o.data.rel);
    const placed = [];
    const v = new THREE.Vector3();
    v.copy(this.center).project(this.camera);
    const nx = (v.x * 0.5 + 0.5) * w;
    const ny = (-v.y * 0.5 + 0.5) * h;
    const nDist = this.camera.position.distanceTo(this.center);
    const nR = (this.nu.uRadius.value * (1 + this.cur.spread) * 1180) / Math.max(nDist, 1);

    for (const { o, i } of order) {
      const el = this.labelEls[i];
      if (!el) continue;
      v.copy(o.g.position).project(this.camera);
      const px = (v.x * 0.5 + 0.5) * w;
      const py = (-v.y * 0.5 + 0.5) * h;
      const dist = this.camera.position.distanceTo(o.g.position);
      const rpx = Math.max(14, (o.baseR * 1100) / Math.max(dist, 1));
      const y = py;
      const clear = (cx) => {
        if (cx < leftBound || cx > w - 150 || y < 66 || y > h - 150) return false;
        const near = Math.max(nx - nR, Math.min(cx + 75, nx + nR));
        if (Math.hypot(near - nx, y - ny) < nR * 0.95 && Math.abs(cx + 75 - nx) < nR + 75) return false;
        for (const p of placed) if (Math.abs(p.x - cx) < 150 && Math.abs(p.y - y) < 26) return false;
        return true;
      };
      let x = px + rpx * 0.85;
      let ok = v.z < 1 && clear(x);
      if (!ok && v.z < 1) {
        const alt = px - rpx * 0.85 - 150;
        if (clear(alt)) {
          x = alt;
          ok = true;
        }
      }
      if (!ok) {
        el.style.opacity = "0";
        continue;
      }
      placed.push({ x, y });
      el.style.transform = `translate3d(${Math.round(x)}px,${Math.round(y - 12)}px,0)`;
      const fade = Math.max(0.28, Math.min(1, 1.5 - dist / 46));
      el.style.opacity = String(this.selected === o || this.hoverObj === o ? 1 : fade * (0.55 + o.data.rel * 0.45));
    }
  }
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

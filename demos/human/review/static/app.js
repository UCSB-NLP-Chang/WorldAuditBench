'use strict';
const $ = id => document.getElementById(id);
const state = {tasks:[],reviewer:null,mode:null,session:null,busy:false,polling:false,saved:null,evidence:null,epoch:0,draftKey:null,reviews:{},rubricLanguage:localStorage.getItem("rubric-language")||"en"};
let entryMode='token',namesReady=false;

let reviewQueue=null,selectedTaskId=null;
const progressFilterIds=['progress-engine','progress-environment','progress-reviewer','progress-result','progress-taxonomy','progress-updated','progress-filter'];
function queueStorageKey(){return 'review-navigation-v1:'+state.reviewer;}
function progressFilters(){return Object.fromEntries(progressFilterIds.map(id=>[id,$(id)?.value||'']));}
function rememberNavigation(){if(!state.reviewer)return;try{sessionStorage.setItem(queueStorageKey(),JSON.stringify({queue:reviewQueue,filters:progressFilters(),current:$('task-select').value,view:$('review-view').hidden?($('progress-view').hidden?'overview':'progress'):'review'}));}catch{}}
function restoreFilters(filters){if(!filters)return;for(const id of progressFilterIds){const el=$(id);if(el&&[...el.options].some(o=>o.value===filters[id]))el.value=filters[id];if(id==='progress-engine')renderProgress();}renderProgress();}
function queueLabel(){const values=progressFilterIds.filter(id=>$(id)?.value).map(id=>$(id).selectedOptions[0]?.textContent).filter(Boolean);return values.join(' · ')||'All tasks';}
function beginReviewQueue(taskId){
 stashDraft();reviewQueue={ids:[...$('progress-rows').querySelectorAll('tr[data-task-id]')].map(row=>row.dataset.taskId),label:queueLabel(),filters:progressFilters()};
 $('environment-select').value='';populateTasks(taskId);renderSession();showView('review');
}
function renderQueue(){
 let box=$('review-queue');if(!box){box=document.createElement('div');box.id='review-queue';box.className='review-queue';$('review-view').prepend(box);}
 box.replaceChildren();const ids=[...$('task-select').options].map(o=>o.value),index=ids.indexOf($('task-select').value);
 box.append(textElement('span',(reviewQueue?.label||($('environment-select').value?$('environment-select').selectedOptions[0].textContent:'All tasks'))+' · '+(index+1)+' of '+ids.length,'queue-position'));
 if(reviewQueue){const back=textElement('button','Back to results','quiet');back.type='button';back.disabled=state.busy;back.onclick=()=>action(returnToResults);box.append(back);}
 selectedTaskId=$('task-select').value;
 if(reviewQueue){reviewQueue.current=selectedTaskId;const url=new URL(location.href);url.searchParams.set('case',selectedTaskId);history.replaceState(null,'',url);}
 rememberNavigation();
}
async function returnToResults(){
 stashDraft();if(hasPendingReview())await saveReview();if(active())await close();
 const filters=reviewQueue?.filters||progressFilters();reviewQueue=null;populateTasks(selectedTaskId);restoreFilters(filters);showView('progress');
}

// Keep taxonomy available while an existing review uses the previous coordinator API.
const taxonomyDefinition={"version":"user-2026-09-18-remove-s1","categories":[{"id":"geometry","name":{"en":"Geometry & space","zh":"几何与空间"},"subcategories":[{"code":"G1","id":"geometry.unsupported","name":{"en":"Missing support / floating","zh":"缺少支撑／悬空"}},{"code":"G2","id":"geometry.intersection","name":{"en":"Intersection / overlap / structural misalignment","zh":"穿插／重叠／结构错位"}},{"code":"G3","id":"geometry.scale","name":{"en":"Scale / proportion mismatch","zh":"尺度／比例失调"}}]},{"id":"collision","name":{"en":"Collision & physics","zh":"碰撞与物理"},"subcategories":[{"code":"C1","id":"collision.missing","name":{"en":"Missing collision","zh":"应阻挡而发生穿透"}},{"code":"C2","id":"collision.unexpected","name":{"en":"Unexpected collision","zh":"不应阻挡却被阻挡"}},{"code":"C3","id":"collision.contact_response","name":{"en":"Abnormal object trajectories after interaction","zh":"交互后物体运动轨迹异常"}}]},{"id":"visual","name":{"en":"Visual consistency","zh":"视觉一致性"},"subcategories":[{"code":"V1","id":"visual.visibility","name":{"en":"Visibility anomalies","zh":"可见性异常"},"definition":{"en":"Object visibility contradicts the current viewpoint, distance or occlusion: an object that should be visible disappears, or an object fully occluded by an opaque surface remains visible.","zh":"物体的可见性不符合当前视角、距离或遮挡关系：应可见时消失，或被不透明物体完全遮挡时仍然可见。"}},{"code":"V2","id":"visual.view_appearance","name":{"en":"View / distance-dependent appearance","zh":"视角／距离相关的外观异常"}},{"code":"V3","id":"visual.illumination","name":{"en":"Shadow / lighting anomalies","zh":"阴影／光照异常"},"definition":{"en":"Light, occlusion or shadow relationships contradict the scene geometry or light sources; darkness or aesthetic preference alone is insufficient.","zh":"光照、遮挡或阴影关系与场景几何或光源矛盾；仅仅太暗或不好看不算异常。"}},{"code":"V4","id":"visual.material","name":{"zh":"材质异常","en":"Material anomalies"},"definition":{"zh":"物体表面的质感、纹理或反光特性与其应有材质明显不符；异常持续存在，不依赖视角、距离或时间变化。仅凭颜色少见或个人审美不足以判错。","en":"An object’s surface character, pattern or reflectance clearly conflicts with its expected material. The anomaly persists independently of viewpoint, distance or time; unusual color or aesthetic preference alone is insufficient."}}],"definition":{"zh":"物体的可见性、外观、光照与场景条件一致，表面质感与其应有材质相符。","en":"Object visibility, appearance and illumination are coherent with scene conditions, and surface character matches the expected material."}},{"id":"state","name":{"en":"Temporal consistency","zh":"时间一致性"},"subcategories":[{"code":"T1","id":"state.existence","name":{"en":"Existence changes","zh":"存在性变化"}},{"code":"T2","id":"state.static_attributes","name":{"en":"Static attribute changes","zh":"静态属性变化"}},{"code":"T3","id":"state.operational_state","name":{"en":"Operational state changes","zh":"动态／运行状态变化"}}],"definition":{"en":"Unexplained changes in existence, static attributes or operational state over time, including after leaving and returning.","zh":"随时间经过或离开再返回，物体的存在、静态属性或运行状态发生无合理原因的变化。"}},{"id":"semantic","name":{"en":"Scene semantic consistency","zh":"场景语义一致性"},"subcategories":[{"code":"S2","id":"semantic.purpose","name":{"zh":"配置不合理","en":"Improper configuration"},"definition":{"zh":"物体符合时代和场景，可以存在，但位置、朝向、组合或使用方式违反明确的场景功能或规则；调整配置即可解决。","en":"The object belongs in this era and scene, but its placement, orientation, combination or use violates an established function or rule. Correcting its configuration resolves the conflict."}},{"code":"S3","id":"semantic.world_setting","name":{"zh":"时代不相容","en":"Historical incompatibility"},"definition":{"zh":"物体或技术因时代原因不应存在于场景中，与明确建立的历史时代不符，且没有穿越、架空或展览等设定解释。","en":"The object or technology should not exist in the established historical era, without an explanation such as time travel, alternate history or an exhibition."}}],"definition":{"zh":"依据明确的场景设定，判断物体是否符合历史时代，以及其位置、朝向、组合或使用方式是否合理。","en":"Given the established scene context, assess whether objects fit its historical era and whether their placement, orientation, combination or use is appropriate."}}],"task_overrides":{"S17":"S2","S19":"S2","S18":"S2","H13":"S2","U028":"S2","A18":"S2","A19":"S2","R12":"S2","MV17":"S2","U039":"S2"}};
function canonicalTaxonomy(task){if(task?.case_type==='baseline')return {};const key=taxonomyDefinition.task_overrides?.[task?.id]||task?.subcategory||task?.taxonomy?.code;for(const category of taxonomyDefinition.categories)for(const sub of category.subcategories)if(sub.code===key||sub.id===key)return {version:taxonomyDefinition.version,category_id:category.id,category:category.name,code:sub.code,subcategory_id:sub.id,subcategory:sub.name};return {};}
function taxonomySummary(tasks){return {version:taxonomyDefinition.version,unclassified:tasks.filter(t=>t.case_type!=='baseline'&&!t.taxonomy?.code).length,categories:taxonomyDefinition.categories.map(category=>{const subcategories=category.subcategories.map(sub=>{const matching=tasks.filter(t=>t.case_type!=='baseline'&&t.taxonomy?.code===sub.code);return {...sub,tasks:matching.length,accepted:matching.filter(t=>t.accepted).length};});return {...category,subcategories,tasks:subcategories.reduce((n,s)=>n+s.tasks,0),accepted:subcategories.reduce((n,s)=>n+s.accepted,0)};})};}
// Shared scene text: generated from environments/review-scene-descriptions.json.
const sceneDescriptions=[{"map": "/Game/Auditor/Regions/BedroomSuite", "task_ids": ["H15"], "description": {"zh": "这是一个带有浴室的卧室。可交互物体是卧室门和窗边的棕色衣柜。", "en": "A bedroom with an adjoining bathroom. Interactive objects: the bedroom door and the brown wardrobe by the window."}}, {"map": "/Game/Auditor/Subway/Concourse", "task_ids": ["B01", "S01", "S05", "S07", "S09", "S12", "S14"], "description": {"en": "An open-air subway entrance with benches, bins and station access routes. No interactive objects.", "zh": "露天的地铁入口，设有长椅、垃圾桶和进站通道。无可交互物体。"}}, {"map": "/Game/Auditor/Subway/Platform", "task_ids": ["B02", "S04", "S06", "S11", "S15", "S16", "S18", "S19", "S20", "S21"], "description": {"en": "A subway waiting area with benches, vending machines and escalators. Some tasks include an interactive bench.", "zh": "地铁候车区，设有长椅、自动售货机和自动扶梯。部分任务中的长椅可交互。"}}, {"map": "/Game/Auditor/Subway/Trackside", "task_ids": ["B03", "S02", "S03", "S08", "S10", "S13"], "description": {"en": "A platform beside the trains, with a walkway, benches and bins. No interactive objects.", "zh": "紧邻列车的站台，设有步行通道、长椅和垃圾桶。无可交互物体。"}}, {"map": "/Game/Auditor/Regions/LivingRoom", "task_ids": ["HB01", "H01", "H07", "H09", "H10"], "description": {"en": "A living room with seating, a television and plants. No interactive objects.", "zh": "摆有座椅、电视和植物的客厅。无可交互物体。"}}, {"map": "/Game/Auditor/Regions/KitchenDining", "task_ids": ["HB02", "H02", "H03", "H04", "H05", "H06", "H08", "H11", "H13"], "description": {"en": "A kitchen and dining area with a refrigerator, table, chairs and tableware. Interactive object: cup.", "zh": "厨房与餐厅，设有冰箱、餐桌、座椅和餐具。可交互物体：杯子。"}}, {"map": "/Game/Auditor/Regions/BedroomSuite", "task_ids": ["HB03", "H12"], "description": {"zh": "这是一个带有浴室的卧室。可交互物体是卧室门和窗边的棕色衣柜。", "en": "A bedroom with an adjoining bathroom. Interactive objects: the bedroom door and the brown wardrobe by the window."}}, {"map": "/Game/Auditor/AncientCity/Market", "task_ids": ["AB01", "A01", "A04", "A06", "A07", "A09", "A11", "A14", "A20", "A22"], "description": {"en": "A market street in an ancient Chinese city, lined with wooden stalls, tables and paper umbrellas. Interactive object: the wicker basket on the ground, which moves a short distance along the ground after a gentle push and then stops.", "zh": "这是一条中国古代城市的集市街道，两侧摆有木制摊位、桌子和纸伞。可交互物体是地上的藤筐，轻推后会沿地面移动一小段，然后停下。"}}, {"map": "/Game/Auditor/AncientCity/TeaHouse", "task_ids": ["AB02", "A03", "A05", "A08", "A12", "A15", "A21", "A24"], "description": {"en": "A tea house in an ancient Chinese city, furnished with wooden tables, benches and hanging lanterns. Its fixed furnishings surround the room and entrance passage.", "zh": "这是一间中国古代城市的茶馆，摆有木桌、长凳，挂有灯笼。家具与灯笼为固定陈设，室内与入口之间留有通道。"}}, {"map": "/Game/Auditor/AncientCity/Courtyard", "task_ids": ["AB03", "A02", "A10", "A13", "A16", "A17", "A19", "A23", "A18", "A25"], "description": {"en": "A residence entrance in an ancient Chinese city, with stone lions, hanging lanterns and two wooden door leaves, one open and one closed. The decorations are fixed, and the two door leaves open and close independently.", "zh": "这是中国古代城市的一处宅院入口，设有石狮、悬挂灯笼和两扇木门，初始一开一关。石狮与灯笼为固定陈设，两扇木门可以分别开关。"}}, {"map": "/Game/Auditor/Industrial/AssemblyHall", "task_ids": ["IB01", "I01", "I02", "I03", "I04", "I05", "I06", "I19"], "description": {"en": "A factory hall with an assembly line, lockers, boxes and chairs. No interactive objects.", "zh": "工厂车间，设有装配线、储物柜、纸箱和座椅。无可交互物体。"}}, {"map": "/Game/Auditor/Industrial/VehicleTest", "task_ids": ["IB02", "I07", "I08", "I09", "I10", "I11", "I12"], "description": {"en": "A vehicle testing and loading area with equipment, rails, bumpers and metal drums. No interactive objects.", "zh": "车辆测试与装卸区，设有设备、轨道、防撞设施和金属桶。无可交互物体。"}}, {"map": "/Game/Auditor/Industrial/ControlRoom", "task_ids": ["IB03", "I13", "I14", "I15", "I16", "I17", "I18", "I20", "I21"], "description": {"zh": "俯瞰工厂车间的控制室，设有照明、监控控制台、座椅和茶几。", "en": "A control room overlooking the factory floor, with lighting, monitoring consoles, chairs and a coffee table."}}, {"map": "/Game/Auditor/RuralAustralia/RoadBend", "task_ids": ["RB01", "R01", "R02", "R03", "R04", "R05", "R06"], "description": {"en": "An Australian bush road bend with wire fences, trees, fallen logs, rocks and wildlife signs. No interactive objects.", "zh": "澳大利亚乡间弯道，两侧有铁丝网、树木、倒木、岩石和野生动物警示牌。无可交互物体。"}}, {"map": "/Game/Auditor/RuralAustralia/Roadside", "task_ids": ["RB02", "R07", "R08", "R09", "R10", "R11", "R12"], "description": {"en": "An Australian country road with signs, trees, fallen logs and fences. No interactive objects.", "zh": "澳大利亚乡间公路，路边有标牌、树木、倒木和围栏。无可交互物体。"}}, {"map": "/Game/Auditor/RuralAustralia/Canyon", "task_ids": ["RB03", "R13", "R14", "R15", "R16", "R17", "R18"], "description": {"en": "An Australian creek canyon with rocks, fallen logs and trees. No interactive objects.", "zh": "澳大利亚溪谷林地，分布着岩石、倒木和树木。无可交互物体。"}}, {"map": "/Game/Auditor/MedievalVillage/Market", "task_ids": ["MVB01", "MV01", "MV02", "MV03", "MV04", "MV05", "MV06", "MV07", "MV08", "MV09", "MV10", "MV19", "MV20", "MV22"], "description": {"zh": "中世纪村庄集市，摆有木制摊位、长凳、木桶和粮食麻袋。可交互物体：篮筐。", "en": "A medieval village market with wooden stalls, benches, barrels and grain sacks. Interactive object: basket."}}, {"map": "/Game/Auditor/MedievalVillage/Windmill", "task_ids": ["MVB02", "MV11", "MV12", "MV13", "MV14", "MV15", "MV16", "MV17", "MV18", "MV21"], "description": {"zh": "中世纪风车庭院，旁边有塔楼、木推车和工坊物料。无可交互物体。", "en": "A medieval windmill courtyard with a tower, wooden cart and workshop supplies. No interactive objects."}}, {"map": "/threejs/00_sponza_constrained.html", "task_ids": ["JS_SP00", "JS_SP01", "JS_SP02", "JS_SP03", "JS_SP04", "JS_SP05", "JS_SP06", "JS_SP07", "JS_SP08", "JS_SP09", "JS_SP10", "JS_SP11", "JS_SP12", "JS_SP13", "JS_SP14", "JS_SP15"], "description": {"en": "An atrium with columns, drapes, stone planters and aisles. No interactive objects.", "zh": "设有柱廊、帷幔、石花盆和通道的中庭。无可交互物体。"}}, {"map": "/threejs/01_mistwood_cottage_constrained.html", "task_ids": ["JS_CT00", "JS_CT01", "JS_CT02", "JS_CT03", "JS_CT04", "JS_CT05", "JS_CT06", "JS_CT07", "JS_CT08", "JS_CT09", "JS_CT10", "JS_CT11", "JS_CT12", "JS_CT13", "JS_CT14", "JS_CT15", "JS_CT16", "JS_CT17"], "description": {"en": "A woodland cottage with a pond, stone paths, trees and outdoor furniture. No interactive objects.", "zh": "林间小屋，周围有池塘、石径、树木和户外家具。无可交互物体。"}}, {"map": "/threejs/03_sketchbook_airfield_constrained.html", "task_ids": ["JS_AF00", "JS_AF01", "JS_AF02", "JS_AF03", "JS_AF04", "JS_AF05", "JS_AF06", "JS_AF07", "JS_AF08", "JS_AF09", "JS_AF10", "JS_AF11", "JS_AF12", "JS_AF13", "JS_AF14", "JS_AF15", "JS_AF16", "JS_AF17", "JS_AF18"], "description": {"en": "An airfield with parked cars, barriers, barrels, crates and workshop equipment. No interactive objects.", "zh": "机场场地，停放着汽车，周围有路障、油桶、箱子和维修设备。无可交互物体。"}}, {"map": "/threejs/09_sims_house_builder_constrained.html", "task_ids": ["JS_HS00", "JS_HS01", "JS_HS02", "JS_HS03", "JS_HS04", "JS_HS05", "JS_HS06", "JS_HS07", "JS_HS08", "JS_HS09", "JS_HS10", "JS_HS11", "JS_HS12", "JS_HS13", "JS_HS14", "JS_HS15"], "description": {"en": "A two-storey home with a kitchen, living room, dining room and upstairs bedrooms. No interactive objects.", "zh": "双层住宅，设有厨房、客厅、餐厅和楼上卧室。无可交互物体。"}}, {"map": "/threejs/10_beautiful_water_clean_constrained.html", "task_ids": ["JS_WT00", "JS_WT01", "JS_WT02", "JS_WT03", "JS_WT04", "JS_WT05", "JS_WT06", "JS_WT07", "JS_WT08", "JS_WT09", "JS_WT10", "JS_WT11", "JS_WT12", "JS_WT13", "JS_WT14", "JS_WT15", "JS_WT16", "JS_WT17"], "description": {"en": "A shallow-water reef with rocks, coral and fish. No interactive objects.", "zh": "分布着岩石、珊瑚和鱼群的浅水礁区。无可交互物体。"}}, {"map": "/threejs/13_beyond_fable_wilderness_constrained.html", "task_ids": ["JS_WL00", "JS_WL01", "JS_WL02", "JS_WL03", "JS_WL04", "JS_WL05", "JS_WL06", "JS_WL07", "JS_WL08", "JS_WL09", "JS_WL10", "JS_WL11", "JS_WL12", "JS_WL13", "JS_WL14", "JS_WL15", "JS_WL16", "JS_WL17"], "description": {"en": "Grassland with pine trees, shrubs and boulders.", "zh": "分布着松树、灌木和岩石的荒野草地。"}}, {"map": "/Game/Auditor/Migration/UE561/U015/R01/TaskMap_Candidate02", "task_ids": ["U015", "U018", "U020", "U023", "U032", "U045"], "description": {"en": "A city intersection with surrounding shops.", "zh": "两侧有店铺的城市路口。"}}, {"map": "/Game/Auditor/Migration/UE561/U011/R01/TaskMap_Candidate02", "task_ids": ["U011", "U013", "U024", "U041", "U043"], "description": {"en": "A rear courtyard with bins, boxes and building entrances.", "zh": "后巷庭院，分布着垃圾桶、纸箱和建筑出入口。"}}, {"map": "/Game/Auditor/Migration/UE561/U012/R01/TaskMap_Candidate02", "task_ids": ["U012", "U014", "U021", "U028", "U046"], "description": {"en": "A shopfront street with outdoor seating, mailboxes and trees.", "zh": "店面街区，设有露天桌椅、邮箱和街边树木。"}}, {"map": "/Game/Auditor/Migration/UE561/U017/R02/TaskMap_Candidate02", "task_ids": ["U017", "U033"], "description": {"en": "A service lane beside buildings, with trees, fences and dumpsters.", "zh": "建筑侧面的服务巷，分布着树木、围栏和垃圾箱。"}}];
const sceneByTask=new Map(sceneDescriptions.flatMap(scene=>scene.task_ids.map(id=>[id,scene])));
// Retain historical 1–5 storage anchors while presenting only three difficulty levels.
function difficultyChoice(value){const n=Number(value);return !Number.isInteger(n)||n<1||n>5?'':String(n<=2?1:n===3?3:5);}
const active = () => state.session && !['closed','failed'].includes(state.session.status);
const mock = () => state.mode === 'mock' || state.session?.mode === 'mock';
function notify(message,error=false){$('notice').textContent=message;$('notice').className=error?'error':'';$('notice').hidden=!message;}
async function api(path,body){
 const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 let data;try{data=await response.json();}catch{throw new Error('The server returned an invalid response. Please try again.');}
 if(!response.ok){const error=new Error(typeof data.error==='string'?data.error:'The request failed. Please try again.');error.status=response.status;throw error;}return data;
}
function loginView(){syncPeerTask(null);document.body.classList.add('at-login');stashDraft();state.epoch++;state.reviewer=null;reviewQueue=null;state.reviews={};state.session=null;state.saved=null;state.evidence=null;state.mode=null;state.draftKey=null;$('identity').hidden=true;$('workspace').hidden=true;$('login-panel').hidden=false;$('demo').hidden=true;$('feedback-form').reset();renderSession();}
function controls(){
 const blocked=state.busy||Boolean(active());$('start').disabled=blocked||!$('task-select').value;$('task-select').disabled=blocked;$('environment-select').disabled=blocked||Boolean(reviewQueue);
 $('close').disabled=state.busy||!active()||state.session.status==='closing';
 $('feedback-fields').disabled=!state.reviewer;
 for(const field of $('feedback-fields').querySelectorAll('input,select,textarea'))field.disabled=state.busy;
 const taskId=$('task-select').value,existing=state.reviews[taskId];const options=[...$('task-select').options],index=options.findIndex(o=>o.value===taskId);$('prev-task').disabled=state.busy||index<=0||['starting','switching','resetting','closing'].includes(state.session?.status);$('next-task').disabled=state.busy||index<0||(!reviewQueue&&index>=options.length-1)||['starting','switching','resetting','closing'].includes(state.session?.status);
 for(const button of $('feedback-form').querySelectorAll('button[type=submit]'))button.disabled=state.busy||(!existing&&(!state.session||taskId!==state.session.task_id||!['ready','failed','closed'].includes(state.session.status)));
 $('next-task').textContent=reviewQueue&&index===options.length-1?'Finish review':'Next';
 renderQueue();
 $('logout').disabled=state.busy;
 $('login-form').querySelector('button').disabled=state.busy;
}
function draftKey(){const task=state.tasks.find(t=>t.id===((active()?state.session.task_id:null)||$('task-select').value));return state.reviewer&&task?'review-draft:'+JSON.stringify([state.mode,state.reviewer,task.id,task.revision,task.sha256,task.build_sha256]):null;}
function stashDraft(){if(!state.draftKey)return;const f=$('feedback-form').elements;const value={difficulty:f.difficulty.value,quality:f.quality.value,comment:f.comment.value,prior_exposure:f.prior_exposure.checked};try{localStorage.setItem(state.draftKey,JSON.stringify(value));}catch{}}
function syncDraft(){const key=draftKey();if(key===state.draftKey)return;stashDraft();state.draftKey=key;state.saveError=null;$('feedback-form').reset();state.saved=null;state.evidence=null;const taskId=active()?state.session.task_id:$('task-select').value;const review=state.reviews[taskId];let draft;try{draft=JSON.parse(localStorage.getItem(key)||'null');}catch{}const d=draft||review;if(d){const f=$('feedback-form').elements;for(const k of ['difficulty','quality','comment'])f[k].value=k==='difficulty'?difficultyChoice(d[k]):d[k]??'';f.prior_exposure.checked=d.prior_exposure===true;if(!draft)state.saved=review?.feedback_id;}}
function markDraft(){state.saved=null;state.saveError=null;stashDraft();renderSaveStatus();}
$('feedback-form').addEventListener('input',markDraft);
$('feedback-form').addEventListener('change',markDraft);
function renderCase(){syncDraft();
 const task=state.tasks.find(t=>t.id===((active()?state.session.task_id:null)||$('task-select').value));
 for(const [field,id] of [['case_id','case-id'],['case_type','case-type']]){
 const value=field==='case_id'?displayTaskId(task):task?.[field];$(id).textContent=value==null?'—':typeof value==='string'?value:JSON.stringify(value,null,2);
 }
 renderContentUpdate(task);
 const box=$('case-rubrics');box.dataset.taskId=task?.id||'';box.replaceChildren();
 document.querySelector('#difficulty + .field-hint').textContent=task?.case_type==='baseline'?'Difficulty of reviewing the scene':'Difficulty of identifying the issue';
 document.querySelector('#quality + .field-hint').textContent=task?.case_type==='baseline'?'Does the scene behave normally?':'Does this task meet the criteria?';
 const lang=state.rubricLanguage==='zh'?'zh':'en';$('rubric-box').hidden=!task||task.case_type==='baseline';box.lang=lang;
 const scene=sceneByTask.get(task?.id);$('scene-box').hidden=!task;$('case-scene').textContent=scene?.description[lang]||task?.scene_i18n?.[lang]||'—';$('case-scene').lang=lang;
 $('rubric-zh').setAttribute('aria-pressed',String(lang==='zh'));$('rubric-en').setAttribute('aria-pressed',String(lang==='en'));
 if(task&&task.case_type!=='baseline'){
  const rubric=task.rubrics_i18n?.[lang];const paragraph=document.createElement('p');paragraph.className='rubric-summary';
  paragraph.textContent=[rubric?.criteria,rubric?.expected].filter(Boolean).join(' ');box.append(paragraph);
 }
 renderTaskTaxonomy($('case-taxonomy'),task);
 syncPeerTask(task?.id);
 for(const key of ['difficulty','quality','comment'])$(key+'-heading').textContent=key[0].toUpperCase()+key.slice(1);
}
function renderSession(){renderCase();
 $('player').classList.toggle('switching',state.session?.status==='switching');
 const s=state.session&&(active()||state.session.task_id===$('task-select').value)?state.session:null;$('demo').hidden=!mock();
 $('session-title').textContent=displayTaskId(s?.task_id||$('task-select').value);
 const labels={queued:'Queued',switching:'Switching task',starting:'Starting',ready:'Ready',failed:'Failed',closed:'Closed',closing:'Closing',resetting:'Resetting'};
 $('session-status').textContent=s?.status==='queued'?'Queued · #'+s.queue_position:s?(labels[s.status]||'Checking status'):'Not started';
 let url=null;
 if((['ready','switching'].includes(s?.status)||(s?.runtime_kind==='browser'&&s.status==='starting'))&&(!mock()||s?.runtime_kind==='browser')&&s.stream_url&&(!$('review-view').hidden||$('player').querySelector('iframe'))){try{const candidate=new URL(s.stream_url,location.href);if(['https:','http:'].includes(candidate.protocol)){if(s.runtime_kind!=='browser'){candidate.searchParams.set('HoveringMouse','false');candidate.searchParams.set('WebRTCMaxBitrate','3000');}url=candidate.href;}}catch{}}
 const frame=$('player').querySelector('iframe');
 if(url){if(!frame||frame.src!==url){$('player').replaceChildren();const f=document.createElement('iframe');f.src=url;f.title='Task game view';f.allow='autoplay; fullscreen; gamepad; clipboard-write';f.allowFullscreen=true;f.referrerPolicy='no-referrer';f.tabIndex=0;f.addEventListener('load',()=>{try{const doc=f.contentDocument;doc.addEventListener('pointerdown',event=>{const video=event.target.closest?.('video');if(video){video.tabIndex=0;f.contentWindow.focus();video.focus({preventScroll:true});}},true);}catch{}});$('player').append(f);if(s.runtime_kind==='browser')watchBrowserFrame(f,s);}}
 else{if(frame)frame.remove();if(!$('stream-placeholder')){const p=document.createElement('div');p.id='stream-placeholder';$('player').append(p);}$('stream-placeholder').textContent=mock()?'Demo mode':s?.error?'Connection interrupted. Start the task again.':s?.status==='starting'?'Starting真实游戏…':'Click Start to connect.';}
 renderSaveStatus();
 controls();
}
function setSession(session){if(state.session?.id!==session?.id){state.saved=null;state.evidence=null;}state.session=session;if(session&&!['closed','failed'].includes(session.status)){if(![...$('task-select').options].some(o=>o.value===session.task_id)){reviewQueue=null;$('environment-select').value='';populateTasks(session.task_id);}$('task-select').value=session.task_id;}renderSession();}
// Stable public numbering; append new assignments without renumbering existing tasks.
const urbanTaskNumbers=Object.freeze({"U011":1,"U012":2,"U013":3,"U014":4,"U015":5,"U017":6,"U018":7,"U020":8,"U021":9,"U023":10,"U024":11,"U028":12,"U032":13,"U033":14,"U039":15,"U041":16,"U043":17,"U045":18,"U046":19});
function displayTaskId(taskOrId){const task=typeof taskOrId==='string'?(state.tasks.find(t=>t.id===taskOrId)||{id:taskOrId}):taskOrId;if(!task)return '—';const id=task.id||'';if(id.startsWith('JS_'))return 'threejs_'+id.slice(3).toLowerCase();if(urbanTaskNumbers[id])return 'unreal_urban_bug_'+String(urbanTaskNumbers[id]).padStart(2,'0');let match;if((match=/^MVB(\d+)$/.exec(id)))return 'unreal_medieval_village_baseline_'+match[1].padStart(2,'0');if((match=/^MV(\d+)$/.exec(id)))return 'unreal_medieval_village_bug_'+match[1].padStart(2,'0');if((match=/^RB(\d+)$/.exec(id)))return 'unreal_rural_baseline_'+match[1].padStart(2,'0');if((match=/^R(\d+)$/.exec(id)))return 'unreal_rural_bug_'+match[1].padStart(2,'0');if((match=/^IB(\d+)$/.exec(id)))return 'unreal_industrial_baseline_'+match[1].padStart(2,'0');if((match=/^I(\d+)$/.exec(id)))return 'unreal_industrial_bug_'+match[1].padStart(2,'0');if((match=/^AB(\d+)$/.exec(id)))return 'unreal_ancient_city_baseline_'+match[1].padStart(2,'0');if((match=/^A(\d+)$/.exec(id)))return 'unreal_ancient_city_bug_'+match[1].padStart(2,'0');if((match=/^HB(\d+)$/.exec(id)))return 'unreal_indoor_baseline_'+match[1].padStart(2,'0');if((match=/^B(\d+)$/.exec(id)))return 'unreal_subway_baseline_'+match[1].padStart(2,'0');if((match=/^([SHU])(\d+)$/.exec(id)))return 'unreal_'+({S:'subway',H:'indoor',U:'urban'}[match[1]])+'_bug_'+String(Number(match[2])).padStart(2,'0');return id;}
function orderedTasks(tasks){const family=t=>({subway:0,indoor:1,urban:2,ancient:3,medieval:6,rural:5,industrial:4,threejs_sponza:7,threejs_cottage:8,threejs_airfield:9,threejs_house:10,threejs_reef:11,threejs_wilderness:12}[t.family]??3),number=t=>Number((t.id||'').match(/\d+$/)?.[0]||0);
 const subtypeOrder=taxonomyDefinition.categories.flatMap(category=>category.subcategories.map(sub=>sub.code));
 const typeRank=task=>{if(task.case_type==='baseline')return -1;const code=canonicalTaxonomy(task).code;const rank=subtypeOrder.indexOf(code);return rank<0?subtypeOrder.length:rank;};
 return [...tasks].sort((a,b)=>family(a)-family(b)||typeRank(a)-typeRank(b)||number(a)-number(b)||String(a.id).localeCompare(String(b.id)));
}
function resolveTaskId(value){return state.tasks.find(t=>t.id===value||displayTaskId(t)===value)?.id||value;}
function taskFamily(task){return task.family||'urban';}
function populateTasks(preferred){const select=$('task-select'),family=$('environment-select').value;select.replaceChildren();if(reviewQueue){for(const id of reviewQueue.ids){const task=state.tasks.find(t=>t.id===id);if(!task)continue;const option=document.createElement('option');option.value=id;option.textContent=displayTaskId(task)+(task.content_update?' · Updated':'');select.append(option);}if([...select.options].some(o=>o.value===preferred))select.value=preferred;return;}const labels={subway:'Subway',indoor:'Indoor',urban:'Urban',ancient:'Ancient Chinese City',medieval:'Medieval Village',rural:'Rural Australia',industrial:'Industrial',threejs_sponza:"Three.js \u00b7 Sponza",threejs_cottage:"Three.js \u00b7 Mistwood Cottage",threejs_airfield:"Three.js \u00b7 Airfield",threejs_house:"Three.js \u00b7 Family House",threejs_reef:"Three.js \u00b7 Reef Dive",threejs_wilderness:"Three.js \u00b7 Wilderness"};for(const key of ['subway','indoor','urban','ancient','industrial','rural','medieval',"threejs_sponza","threejs_cottage","threejs_airfield","threejs_house","threejs_reef","threejs_wilderness"]){const tasks=state.tasks.filter(t=>taskFamily(t)===key&&(!family||key===family));if(!tasks.length)continue;const group=document.createElement('optgroup');group.label=labels[key];for(const task of tasks){const option=document.createElement('option');option.value=task.id;option.textContent=displayTaskId(task)+(task.content_update?' · Updated':'');group.append(option);}select.append(group);}if([...select.options].some(o=>o.value===preferred))select.value=preferred;}
async function loadTasks(){const data=await api('/api/tasks');state.mode=data.mode;state.tasks=orderedTasks(data.tasks.map(task=>({...task,taxonomy:canonicalTaxonomy(task)})));populateTasks(resolveTaskId(new URLSearchParams(location.search).get('case')));renderSession();}
$('environment-select').onchange=()=>{populateTasks($('task-select').value);renderSession();};

let dashboardData=null,taxonomyMode='all',taxonomyEngine='unreal';
function engineOf(task){return task.family?.startsWith('threejs_')?'threejs':'unreal';}
function renderEngineStats(data){
 for(const engine of ['unreal','threejs']){
  const tasks=data.tasks.filter(t=>engineOf(t)===engine),bugs=tasks.filter(t=>t.case_type!=='baseline');
  const counts={environments:new Set(tasks.map(t=>t.family)).size,scenes:new Set(tasks.map(t=>JSON.stringify([t.family,t.scene]))).size,tasks:bugs.length,'single-approval':bugs.filter(t=>t.approvals===1).length,accepted:bugs.filter(t=>t.accepted).length};
  const prefix=engine==='threejs'?'stat-threejs-':'stat-';
  for(const [key,value] of Object.entries(counts)){const node=$(prefix+key);if(node)node.textContent=value;}
  const baseline=$(prefix+'baselines');if(baseline)baseline.textContent='+ '+(tasks.length-bugs.length)+' baseline checks';
 }
}
function showView(view){$('progress-view').hidden=view!=='progress';$('nav-progress').classList.toggle('selected',view==='progress');$('dashboard').hidden=view!=='overview';$('review-view').hidden=view!=='review';$('nav-overview').classList.toggle('selected',view==='overview');$('nav-review').classList.toggle('selected',view==='review');renderSession();resizeReview();}
function resizeReview(){const el=document.querySelector('.review-layout');el.style.height=innerWidth>960?Math.max(440,innerHeight-el.getBoundingClientRect().top-window.scrollY-20)+'px':'';}
window.addEventListener('resize',resizeReview);
$('nav-progress').onclick=()=>{renderProgress();showView('progress');};
$('nav-overview').onclick=()=>showView('overview');$('nav-review').onclick=$('browse-tasks').onclick=()=>showView('review');
function textElement(tag,text,className){const el=document.createElement(tag);el.textContent=text;if(className)el.className=className;return el;}
function sceneName(scene){const urban={junction:'Junction',rear_lane:'Rear lane courtyard',shopfront:'Shopfront',service_lane:'Service lane'};if(urban[scene])return urban[scene];return {AssemblyHall:'Assembly hall',VehicleTest:'Vehicle test & loading bay',ControlRoom:'Control room',Market:'Market street',TeaHouse:'Tea house',Courtyard:'Residence entrance',LivingRoom:'Living room',KitchenDining:'Kitchen & dining',BedroomSuite:'Bedroom & bathroom',TaskMap_Candidate01:'City block'}[scene]||scene;}
function renderDashboard(data){data.tasks=orderedTasks(data.tasks.map(task=>({...task,taxonomy:canonicalTaxonomy(state.tasks.find(t=>t.id===task.id)||task)})));data.taxonomy=taxonomySummary(data.tasks);dashboardData=data;renderEngineStats(data);$('dashboard-updated').textContent='Live · updates every 3s';$('capacity-summary').textContent=data.running.length+' / '+data.capacity+' slots in use · '+Math.max(0,data.capacity-data.running.length)+' available';
 const slots=$('running-slots');slots.replaceChildren();for(let i=1;i<=data.capacity;i++){const session=data.running.find(s=>s.slot===i),card=textElement('article','',session?'slot occupied':'slot');card.append(textElement('span','SLOT '+i,'slot-label'),textElement('h3',session?session.reviewer:'Available'),textElement('p',session?displayTaskId(session.task_id)+' · '+({ready:'Ready',switching:'Switching task',starting:'Starting',resetting:'Resetting',closing:'Finishing'}[session.status]||session.status):'Ready for the next reviewer'));if(session?.mine){const b=textElement('button','Open your review →','quiet');b.onclick=()=>showView('review');card.append(b);}if(session){const task=data.tasks.find(t=>t.id===session.task_id);card.append(textElement('small',taxonomyShort(task),'slot-taxonomy'));}slots.append(card);}
 $('waiting-count').textContent=data.queue.length;const waiting=$('waiting-list');waiting.replaceChildren();if(!data.queue.length)waiting.append(textElement('p','No one is waiting.','empty-queue'));for(const session of data.queue){const row=textElement('div','','waiting-row');row.append(textElement('span',String(session.position),'queue-number'),textElement('strong',session.reviewer+(session.mine?' (you)':'')),textElement('span',displayTaskId(session.task_id)),textElement('small',taxonomyShort(data.tasks.find(t=>t.id===session.task_id)),'queue-taxonomy'));if(session.mine){const cancel=textElement('button','Leave queue','quiet');cancel.onclick=()=>action(async()=>{await close();await loadDashboard();});row.append(cancel);}waiting.append(row);}renderTaxonomyOverview();renderProgress();}
function syncProgressOptions(select, entries, emptyLabel){
 const current=select.value;
 const signature=JSON.stringify(entries);
 if(select.dataset.entries===signature)return;
 select.replaceChildren(new Option(emptyLabel,''));
 for(const [value,label] of entries)select.append(new Option(label,value));
 select.value=entries.some(([value])=>value===current)?current:'';
 select.dataset.entries=signature;
}
function progressEnvironmentName(family){return ({subway:'Subway',indoor:'Indoor',urban:'Urban',ancient:'Ancient Chinese City',medieval:'Medieval Village',rural:'Rural Australia',industrial:'Industrial',threejs_sponza:'Three.js · Sponza',threejs_cottage:'Three.js · Mistwood Cottage',threejs_airfield:'Three.js · Airfield',threejs_house:'Three.js · Family House',threejs_reef:'Three.js · Reef Dive',threejs_wilderness:'Three.js · Wilderness'}[family]||family);}
function latestProgressReview(task,reviewer,mine){
 const id=reviewer||mine;
 if(Array.isArray(task.latest_reviewer_results))return task.latest_reviewer_results.find(r=>r.id===id);
 const quality=reviewer?task.reviewer_results?.find(r=>r.id===reviewer)?.quality:task.my_quality;
 return quality?{quality,current_version:true}:null;
}
function matchesReviewResult(quality,result){return !result||(result==='follow-up'?quality==='fail'||quality==='uncertain':quality===result);}
function renderProgress(){
 if(!dashboardData)return;
 const engine=$('progress-engine').value;
 const families=[...new Set(dashboardData.tasks.filter(t=>!engine||engineOf(t)===engine).map(t=>taskFamily(t)))];
 syncProgressOptions($('progress-environment'),families.map(f=>[f,progressEnvironmentName(f)]),'All environments');
 syncProgressOptions($('progress-reviewer'),(dashboardData.reviewer_options||[]).map(r=>[r.id,r.name+(r.mine?' (you)':'')]),'All reviewers');
 const reviewer=$('progress-reviewer').value,environment=$('progress-environment').value;
 const person=dashboardData.reviewer_options?.find(r=>r.id===reviewer);
 $('progress-review-heading').textContent=person?person.name+' · Review':'Your review';
 const body=$('progress-rows'),filter=$('progress-filter').value,selectedType=$('progress-taxonomy').value,resultFilter=$('progress-result').value;
 const updateFilter=$('progress-updated')?.value||'';
 const mine=dashboardData.reviewer_options?.find(r=>r.mine)?.id;
 body.replaceChildren();
 for(const task of dashboardData.tasks){
  if(engine&&engineOf(task)!==engine)continue;
  if(environment&&taskFamily(task)!==environment)continue;
  if(updateFilter==='updated'&&!task.content_update||updateFilter==='not-updated'&&task.content_update)continue;
  if(selectedType==='baseline'?task.case_type!=='baseline':selectedType&&(task.case_type==='baseline'||task.taxonomy?.code!==selectedType))continue;
  if(filter==='review'&&task.accepted||filter==='accepted'&&!task.accepted)continue;
  const review=latestProgressReview(task,reviewer,mine),quality=review?.quality;
  if(!matchesReviewResult(quality,resultFilter))continue;
  if(reviewer&&!quality)continue;
  const row=document.createElement('tr');row.dataset.taskId=task.id;
  const id=textElement('td',displayTaskId(task));if(task.content_update)id.append(updatedBadge(task));
  const world=textElement('td',progressEnvironmentName(taskFamily(task))+' / '+sceneName(task.scene));
  const approval=textElement('td',task.approvals+' / 2');
  if(task.reviewers.length)approval.append(textElement('small',task.reviewers.join(', '),'approval-names'));
  const status=document.createElement('td');status.append(textElement('span',task.accepted?'Accepted':'Review',task.accepted?'status-pill accepted':'status-pill'));
  const result=textElement('td',quality?{pass:'Pass',fail:'Fail',uncertain:'Uncertain'}[quality]:'—','progress-quality '+(quality||''));
  if(review&&review.current_version===false){const note=textElement('small',review.counts_toward_current?'Earlier build · compatible':'Previous version');note.style.display='block';result.append(note);}
  const actionCell=document.createElement('td'),button=textElement('button','Review →','quiet');
  button.disabled=Boolean(active())||state.busy;button.onclick=()=>beginReviewQueue(task.id);actionCell.append(button);
  const bugType=textElement('td','','progress-bug-type');renderProgressType(bugType,task);
  const totalReviews=textElement('td',String(task.total_reviews??0));totalReviews.title='Number of review tags: one per reviewer and reviewed version; repeated edits count once';
  row.append(id,world,bugType,approval,totalReviews,status,result,actionCell);body.append(row);
 }
 rememberNavigation();
 $('progress-result-count').textContent=body.children.length+' of '+dashboardData.tasks.length+' review entries'+(person?' · '+person.name+'’s reviewed tasks':'');
 if(!body.children.length){const row=document.createElement('tr'),cell=textElement('td',person?'No reviewed tasks match these filters.':'No tasks in this view.');cell.colSpan=8;row.append(cell);body.append(row);}
}
$('progress-updated')?.addEventListener('change',renderProgress);
$('progress-engine').onchange=renderProgress;
for(const id of ['progress-environment','progress-reviewer','progress-filter','progress-taxonomy'])$(id).onchange=renderProgress;
$('progress-result').onchange=()=>{if($('progress-result').value){if(!$('progress-reviewer').value)$('progress-reviewer').value=dashboardData?.reviewer_options?.find(r=>r.mine)?.id||'';$('progress-filter').value='';}renderProgress();};

function taxonomyShort(task){return task?.taxonomy?.code?task.taxonomy.subcategory.en:task?.case_type==='baseline'?'Baseline · no injected bug':(task?.kind||'Unclassified');}
function renderProgressType(target,task){target.replaceChildren();if(task.case_type==='baseline'){target.textContent='Baseline';return;}if(!task.taxonomy?.code){target.textContent=task.kind?task.category+' · '+task.kind:'Unclassified';return;}target.append(textElement('span',task.taxonomy.category.en,'taxonomy-category-label'),textElement('strong',task.taxonomy.subcategory.en,'taxonomy-subtype-label'));}
function renderTaskTaxonomy(target,task){target.replaceChildren();if(!task){target.textContent='—';return;}if(!task.taxonomy?.code){target.append(textElement('span',task.case_type==='baseline'?'Baseline':task.kind?task.category+' · '+task.kind+' (service subtype unmapped / 服务细分类待映射)':'Unclassified · 未分类'));return;}const t=task.taxonomy,lang=state.rubricLanguage==='zh'?'zh':'en';target.dataset.category=t.category_id;target.append(textElement('span',t.category[lang],'taxonomy-category-label'),textElement('strong',t.subcategory[lang],'taxonomy-subtype-label'));}
function renderTaxonomyOverview(){if(!dashboardData)return;const scoped=dashboardData.tasks.filter(t=>engineOf(t)===taxonomyEngine),taxonomy=taxonomySummary(scoped);if($('taxonomy-unreal'))$('taxonomy-unreal').setAttribute('aria-pressed',String(taxonomyEngine==='unreal'));if($('taxonomy-threejs'))$('taxonomy-threejs').setAttribute('aria-pressed',String(taxonomyEngine==='threejs'));const unmapped=scoped.filter(t=>t.case_type!=='baseline'&&!t.taxonomy?.code&&(taxonomyMode!=='accepted'||t.accepted)).length;if($('taxonomy-scope'))$('taxonomy-scope').textContent=(taxonomyEngine==='threejs'?'Three.js':'Unreal')+' · '+(taxonomyMode==='accepted'?'Accepted bug tasks':'All bug tasks')+(unmapped?' · '+unmapped+' unclassified (excluded from percentages)':'');const field=taxonomyMode==='accepted'?'accepted':'tasks',total=taxonomy.categories.reduce((n,c)=>n+c[field],0);const container=$('taxonomy-categories');container.replaceChildren();
 $('taxonomy-all').setAttribute('aria-pressed',String(taxonomyMode==='all'));$('taxonomy-accepted').setAttribute('aria-pressed',String(taxonomyMode==='accepted'));
 for(const category of taxonomy.categories){const count=category[field],percentage=total?100*count/total:0;const card=textElement('article','','taxonomy-card');card.dataset.category=category.id;const header=textElement('div','','taxonomy-card-heading');header.append(textElement('h3',category.name.en),textElement('span',category.name.zh,'taxonomy-zh'),textElement('strong',total?percentage.toFixed(1)+'%':'0%','taxonomy-percentage'),textElement('p',(total?count+' / '+total:'0')+(taxonomyMode==='accepted'?' accepted tasks':' tasks'),'taxonomy-counts'));const bar=textElement('div','','taxonomy-share-bar'),fill=textElement('span','');fill.style.width=percentage+'%';bar.append(fill);bar.setAttribute('aria-hidden','true');header.append(bar);card.append(header);
 const rows=textElement('div','','taxonomy-types');for(const sub of category.subcategories){const button=textElement('button','','taxonomy-type');button.dataset.code=sub.code;if(sub.definition)button.title=sub.definition.en+'\n'+sub.definition.zh;const title=textElement('span','','taxonomy-type-title');title.append(textElement('span',sub.name.en),textElement('small',sub.name.zh));const count=textElement('span',sub[field]+(taxonomyMode==='accepted'?' accepted':sub[field]===1?' task':' tasks'),'taxonomy-type-count');button.append(title,count);button.setAttribute('aria-label',sub.name.en+', '+sub[field]+(taxonomyMode==='accepted'?' accepted tasks':' tasks'));button.onclick=()=>{if($('progress-engine'))$('progress-engine').value=taxonomyEngine;$('progress-environment').value='';$('progress-reviewer').value='';$('progress-result').value='';$('progress-taxonomy').value=sub.code;$('progress-filter').value=taxonomyMode==='accepted'?'accepted':'review';renderProgress();showView('progress');window.scrollTo({top:0,behavior:'instant'});};rows.append(button);}card.append(rows);container.append(card);}
 if($('progress-taxonomy').options.length===1){$('progress-taxonomy').append(new Option('Baseline','baseline'));for(const category of taxonomy.categories){const group=document.createElement('optgroup');group.label=category.name.en;for(const sub of category.subcategories)group.append(new Option(sub.name.en,sub.code));$('progress-taxonomy').append(group);}}
}
if($('taxonomy-unreal'))$('taxonomy-unreal').onclick=()=>{taxonomyEngine='unreal';renderTaxonomyOverview();};
if($('taxonomy-threejs'))$('taxonomy-threejs').onclick=()=>{taxonomyEngine='threejs';renderTaxonomyOverview();};
$('taxonomy-all').onclick=()=>{taxonomyMode='all';renderTaxonomyOverview();};$('taxonomy-accepted').onclick=()=>{taxonomyMode='accepted';renderTaxonomyOverview();};
async function loadDashboard(){renderDashboard(await api('/api/dashboard'));await loadPeerReviews();}

let peerTask=null,peerRequest=0,peerLoading=false,peerSignature=null,peerRows=null,peerMine=[],peerError=false;
function updatedBadge(task){const badge=textElement('span','Updated','updated-badge');badge.title='Content updated '+task.content_update.published_on;return badge;}
function renderContentUpdate(task){
 const box=$('case-update'),expanded=box.dataset.taskId===task?.id&&Boolean(box.querySelector('details')?.open);box.dataset.taskId=task?.id||'';box.replaceChildren();box.hidden=!task?.content_update;if(!task?.content_update)return;
 const update=task.content_update,lang=state.rubricLanguage==='zh'?'zh':'en';
 box.append(updatedBadge(task),textElement('time',update.published_on,'update-date'));
 const changes=document.createElement('details');changes.open=expanded;changes.append(textElement('summary','What changed'),textElement('p',update.summary_i18n?.[lang]||update.summary_i18n?.en||''));box.append(changes);
 const note=textElement('p','','update-personal');note.id='updated-since-review';note.hidden=true;box.append(note);
}
function reviewIsCurrent(review){
 if(typeof review.current_version==='boolean')return review.current_version;
 const task=state.tasks.find(t=>t.id===peerTask);
 return Boolean(task&&['revision','sha256','build_sha256'].every(k=>review[k]===task[k]));
}
function renderReviewStatus(){
 const box=$('case-review-status');if(!box)return;const expanded=box.dataset.taskId===peerTask&&Boolean(box.querySelector('details')?.open);box.dataset.taskId=peerTask||'';box.replaceChildren();box.hidden=!peerTask;
 if(!peerTask||!state.reviewer)return;
 const own=peerRows===null&&state.reviews[peerTask]?[{reviewer:state.reviewer,quality:state.reviews[peerTask].quality,current_version:true}]:peerMine;
 const rows=[...own,...(peerRows||[])].filter(r=>['pass','fail','uncertain'].includes(r.quality));
 const current=rows.filter(reviewIsCurrent),previous=rows.filter(r=>!reviewIsCurrent(r));
 const labels={pass:'Passed',uncertain:'Uncertain',fail:'Failed'};
 const group=(parent,reviews)=>{for(const review of reviews)parent.append(textElement('span',review.reviewer+' · '+labels[review.quality],'review-result '+review.quality));};
 box.append(textElement('span','Current version','review-group-label'));group(box,current);
 if(peerRows===null)box.append(textElement('span',peerError?'Could not load reviewer results.':'Loading reviewer results…','review-result-note'));
 else if(!current.length)box.append(textElement('span','No reviews for this version yet.','review-result-note'));
 if(previous.length){const details=document.createElement('details');details.className='previous-reviews';details.open=expanded;details.append(textElement('summary','Previous versions · '+previous.length+' reviews'));group(details,previous);box.append(details);}
 const note=$('updated-since-review');if(note){note.hidden=!(peerMine.some(r=>!reviewIsCurrent(r))&&!peerMine.some(reviewIsCurrent));note.textContent='Updated since your last review';}
}
function syncPeerTask(taskId){
 if(peerTask===taskId){renderReviewStatus();if(peerSignature===null)loadPeerReviews();return;}
 peerTask=taskId;peerRequest++;peerLoading=false;peerSignature=null;peerRows=null;peerMine=[];peerError=false;
 $('peer-reviews').open=false;$('peer-reviews').hidden=!taskId;
 $('peer-review-list').replaceChildren();renderReviewStatus();loadPeerReviews();
}
async function loadPeerReviews(){
 if(!state.reviewer||!peerTask||peerLoading||($('review-view').hidden&&!$('peer-reviews').open))return;
 const taskId=peerTask,request=++peerRequest;peerLoading=true;
 const list=$('peer-review-list');if(peerSignature===null)list.replaceChildren(textElement('p','Loading reviews…','peer-empty'));
 try{
  const [data,history]=await Promise.all([api('/api/tasks/'+encodeURIComponent(taskId)+'/reviews'),api('/api/reviews/history')]);
  if(request!==peerRequest||taskId!==peerTask)return;
  // Keep every reviewed version, with the latest saved rating for each version.
  const mine=new Map();
  for(const review of history.review_history||[]){
   if(review.task_id!==taskId||review.mode!==state.mode)continue;
   mine.set(JSON.stringify([review.revision,review.sha256,review.build_sha256]),review);
  }
  peerMine=[...mine.values()].sort((a,b)=>b.created-a.created);
  peerRows=data.reviews;peerError=false;renderReviewStatus();
  const signature=JSON.stringify(data.reviews);if(signature===peerSignature)return;
  peerSignature=signature;list.replaceChildren();
  if(!data.reviews.length)list.append(textElement('p','No reviews from other reviewers yet.','peer-empty'));
  const currentGroup=textElement('section','','review-version-group');currentGroup.append(textElement('h4','Current version'));list.append(currentGroup);
  const previousGroup=document.createElement('details');previousGroup.className='previous-reviews';previousGroup.append(textElement('summary','Previous versions · '+data.reviews.filter(r=>!r.current_version).length+' reviews'));if(data.reviews.some(r=>!r.current_version))list.append(previousGroup);
  if(!data.reviews.some(r=>r.current_version))currentGroup.append(textElement('p','No reviews for this version yet.','peer-empty'));
  for(const review of data.reviews){
   const card=textElement('article','','peer-review'),heading=textElement('div','','peer-review-heading');
   heading.append(textElement('strong',review.reviewer),textElement('span',({pass:'Pass',fail:'Fail',uncertain:'Uncertain'})[review.quality]||'—','peer-quality '+review.quality));
   card.append(heading);
   const difficulty=({'1':'Easy','3':'Medium','5':'Hard'})[difficultyChoice(review.difficulty)]||'—';
   card.append(textElement('p','Difficulty: '+difficulty,'peer-meta'));
   if(!review.current_version)card.append(textElement('p',review.counts_toward_current?'Earlier build · unchanged task · counts toward acceptance':'Previous version · does not count toward acceptance','peer-version'));
   card.append(textElement('p',review.comment||'No comment.','peer-comment'));
   const time=document.createElement('time');time.dateTime=new Date(review.updated_at*1000).toISOString();time.textContent='Updated '+new Date(review.updated_at*1000).toLocaleString();card.append(time);(review.current_version?currentGroup:previousGroup).append(card);
  }
 }catch(error){if(request===peerRequest){peerSignature=null;peerRows=null;peerError=true;renderReviewStatus();list.replaceChildren(textElement('p','Could not load reviews. Close and reopen to retry.','peer-empty'));}}
 finally{if(request===peerRequest)peerLoading=false;}
}
$('peer-reviews').addEventListener('toggle',()=>{if($('peer-reviews').open)loadPeerReviews();});

async function enter(reviewer,local=false){document.body.classList.remove('at-login');$('logout').hidden=local;state.reviewer=reviewer;$('reviewer-name').textContent=reviewer;$('identity').hidden=false;$('login-panel').hidden=true;$('workspace').hidden=false;let saved;try{saved=JSON.parse(sessionStorage.getItem(queueStorageKey())||'null');}catch{}state.reviews=(await api('/api/reviews')).reviews;await loadTasks();setSession((await api('/api/sessions/current')).session);showView('overview');await loadDashboard();
 const direct=resolveTaskId(new URLSearchParams(location.search).get('case'));
 if(saved&&(!direct||direct===saved.current)){
  restoreFilters(saved.filters);
  const ids=Array.isArray(saved.queue?.ids)?saved.queue.ids.filter(id=>state.tasks.some(t=>t.id===id)):[];
  if(ids.length&&(!active()||ids.includes(state.session.task_id))){reviewQueue={...saved.queue,ids};$('environment-select').value='';populateTasks(active()?state.session.task_id:saved.current);}
  else if(!active())populateTasks(saved.current);
  showView(['review','progress','overview'].includes(saved.view)?saved.view:'overview');
 }else if(direct)showView('review');
}
async function action(fn){if(state.busy)return;state.busy=true;state.epoch++;controls();try{await fn();}catch(error){notify(error.message,true);if(error.status===401)loginView();}finally{state.busy=false;controls();}}
async function start(task){const result=await api('/api/sessions',task?{task_id:task}:{});setSession(result.session);showView('review');await loadDashboard();notify(result.session.runtime_kind==='browser'?'Loading environment…':'Session requested. Your place is shown in the live queue.');}
async function close(){if(!state.session)return;await api(`/api/sessions/${encodeURIComponent(state.session.id)}/close`,{});for(let i=0;i<30;i++){setSession((await api('/api/sessions/current')).session);if(!state.session||['closed','failed'].includes(state.session.status))return;await new Promise(resolve=>setTimeout(resolve,1000));}throw new Error('反馈保留，结束会话仍在处理中，请稍后重试。');}
function setNames(reviewers){const selected=$('reviewer').value;$('reviewer').replaceChildren(new Option('Select your name',''));for(const reviewer of reviewers)$('reviewer').append(new Option(reviewer.name,reviewer.name));$('reviewer').value=selected;}
async function loadNames(){const data=await api('/api/participants',{access_code:$('token').value});setNames(data.reviewers);namesReady=true;}
$('token').addEventListener('input',()=>{namesReady=false;});
$('token').addEventListener('blur',()=>{if(entryMode==='group'&&$('token').value&&!namesReady)loadNames().catch(()=>{});});
$('login-form').addEventListener('submit',event=>{event.preventDefault();action(async()=>{
 const reviewer=$('reviewer').value.trim();if(!reviewer)throw new Error('Please select your name.');
 if(entryMode==='group'&&!namesReady)await loadNames();
 const data=await api(entryMode==='token'?'/api/login':'/api/participant-login',entryMode==='token'?{token:$('token').value,reviewer}:{access_code:$('token').value,reviewer});$('token').value='';await enter(data.reviewer);notify('Signed in as '+data.reviewer+'.');
});});
async function configureEntry(){const entry=await api('/api/entry');entryMode=entry.mode;namesReady=false;setNames(entry.reviewers||[]);$('access-label').hidden=entryMode==='name';$('token').required=entryMode!=='name';$('access-title').textContent=entryMode==='group'?'Passcode':'Access token';$('token').placeholder=entryMode==='group'?'Group passcode':'Access token';$('name-label').hidden=false;$('reviewer').required=true;$('login-form').querySelector('button').textContent='Enter';if(entryMode==='name')await loadNames();}

$('logout').onclick=()=>action(async()=>{if(active())await close();await api('/api/logout',{});loginView();await configureEntry();notify('Signed out.');});
$('start').onclick=()=>action(()=>start($('task-select').value));
$('close').onclick=()=>action(async()=>{await close();notify('Session ended. Unsubmitted edits remain as drafts.');});
$('task-select').onchange=()=>{const next=$('task-select').value;$('task-select').value=selectedTaskId;action(()=>moveToTask(next));};
$('evidence').onchange=()=>{state.evidence=null;};
async function uploadEvidence(sessionId){
 const file=$('evidence').files[0];if(!file)return [];
 if(!['image/png','image/jpeg'].includes(file.type)||file.size>5*1024*1024)throw new Error('截图仅支持 PNG/JPEG，文件不能超过 5 MiB。');
 if(state.evidence?.file===file)return [state.evidence.id];
 const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('读取截图失败。'));reader.readAsDataURL(file);});
 const result=await api(`/api/sessions/${encodeURIComponent(sessionId)}/evidence`,{filename:file.name,content_base64:content,mime_type:file.type});state.evidence={file,id:result.evidence_id};return [result.evidence_id];
}
$('rubric-zh').onclick=()=>setRubricLanguage('zh');$('rubric-en').onclick=()=>setRubricLanguage('en');
function setRubricLanguage(lang){state.rubricLanguage=lang;try{localStorage.setItem('rubric-language',lang);}catch{}renderCase();}
async function navigateTask(delta){
 const ids=[...$('task-select').options].map(o=>o.value),index=ids.indexOf($('task-select').value),next=ids[index+delta];
 if(!next){if(reviewQueue&&delta===1&&index===ids.length-1)await returnToResults();return;}
 await moveToTask(next);
}
async function moveToTask(next){
 if(![...$('task-select').options].some(o=>o.value===next))return;
 stashDraft();if(hasPendingReview())await saveReview();
 const source=state.tasks.find(t=>t.id===state.session?.task_id),target=state.tasks.find(t=>t.id===next);
 if(state.session?.status==='ready'&&source?.runtime_switch&&target?.runtime_switch&&((source.runtime_kind==='browser'&&target.runtime_kind==='browser')||(source.family===target.family&&source.build_sha256===target.build_sha256))){
  const result=await api(`/api/sessions/${encodeURIComponent(state.session.id)}/switch`,{task_id:next});setSession(result.session);showView('review');await loadDashboard();notify(target.runtime_kind==='browser'?'Loading next task…':'Switching task. Your current slot is reserved.');return;
 }
 const wasActive=Boolean(active());if(wasActive)await close();$('task-select').value=next;renderSession();if(wasActive)await start(next);else showView('review');
}
$('prev-task').onclick=()=>action(()=>navigateTask(-1));$('next-task').onclick=()=>action(()=>navigateTask(1));
function reviewValues(value){return {difficulty:difficultyChoice(value.difficulty),quality:value.quality||'',comment:(value.comment||'').trim(),prior_exposure:value.prior_exposure===true};}
function currentReviewValues(){const f=$('feedback-form').elements;return reviewValues({difficulty:f.difficulty.value,quality:f.quality.value,comment:f.comment.value,prior_exposure:f.prior_exposure.checked});}
function hasPendingReview(){
 const value=currentReviewValues(),previous=state.reviews[$('task-select').value];
 if($('evidence').files.length)return true;
 if(previous)return JSON.stringify(value)!==JSON.stringify(reviewValues(previous));
 return Boolean(value.difficulty||value.quality||value.comment||value.prior_exposure);
}
function renderSaveStatus(){
 const dirty=hasPendingReview();
 $('saved-note').textContent=state.savingReview?'Saving to server…':state.saveError?'Not saved · '+state.saveError:dirty?'Draft saved on this device · Next / Prev saves to server.':state.reviews[$('task-select').value]?'Saved to server.':'Next / Prev saves your review automatically.';
}
async function saveReview(){
 stashDraft();const taskId=$('task-select').value,s=state.session,values=currentReviewValues();
 state.saveError=null;state.savingReview=true;renderSaveStatus();
 try{
  if(!values.difficulty||!['pass','fail','uncertain'].includes(values.quality))throw new Error('Select difficulty and quality before saving or switching tasks.');
  let previous=state.reviews[taskId];
  const matchingSession=s?.task_id===taskId&&['ready','failed','closed'].includes(s.status);
  let useNewSession=matchingSession&&s.id!==previous?.session_id;
  const sid=useNewSession?s.id:previous?.session_id||(matchingSession?s.id:null);
  if(!sid)throw new Error('Start this task before saving your first review. Your draft is kept on this device.');
  // Recover a successful first submission whose response was lost, without duplicating it.
  if(!previous||useNewSession){
   const latest=(await api('/api/reviews')).reviews[taskId];
   if(latest?.session_id===sid){previous=latest;useNewSession=false;state.reviews[taskId]=latest;}
  }
  const evidence_ids=[...new Set([...(useNewSession?[]:previous?.evidence_ids||[]),...await uploadEvidence(sid)])];
  const data={...values,difficulty:Number(values.difficulty),evidence_ids};
  if(previous&&!useNewSession){const result=await api('/api/reviews/'+encodeURIComponent(previous.feedback_id),{...data,updated_at:previous.updated_at});state.reviews[taskId]=result.review;}
  else{await api(`/api/sessions/${encodeURIComponent(sid)}/feedback`,data);state.reviews=(await api('/api/reviews')).reviews;}
  const saved=state.reviews[taskId];
  if(!saved||saved.session_id!==sid||JSON.stringify(reviewValues(saved))!==JSON.stringify(values)||JSON.stringify([...(saved.evidence_ids||[])].sort())!==JSON.stringify([...evidence_ids].sort()))throw new Error('Could not confirm the saved review. Your draft is kept; retry before switching tasks.');
  state.saved=state.reviews[taskId].feedback_id;
  // Invalidate in-flight history reads from before this save.
  peerRequest++;peerLoading=false;peerSignature=null;peerRows=null;peerMine=[];peerError=false;
  try{localStorage.removeItem(state.draftKey);}catch{}
  $('evidence').value='';state.evidence=null;
 }catch(error){state.saved=null;state.saveError=error.message;stashDraft();throw error;}
 finally{state.savingReview=false;renderSession();}
}
$('feedback-form').addEventListener('submit',event=>{event.preventDefault();action(async()=>{await saveReview();await loadDashboard();notify('Review saved.');});});
async function poll(){if(!state.reviewer||state.busy||state.polling)return;state.polling=true;const epoch=state.epoch;try{const [result,dashboard]=await Promise.all([api('/api/sessions/current'),api('/api/dashboard')]);if(epoch!==state.epoch)return;renderDashboard(dashboard);setSession(result.session);await loadPeerReviews();if(active())await api(`/api/sessions/${encodeURIComponent(state.session.id)}/heartbeat`,{});}catch(error){if(epoch===state.epoch){notify('连接异常：'+error.message,true);if(error.status===401)loginView();}}finally{state.polling=false;}}
window.addEventListener('beforeunload',event=>{if(active()&&!state.saved&&($('feedback-form').elements.comment.value||$('feedback-form').elements.difficulty.value||$('feedback-form').elements.quality.value)){event.preventDefault();event.returnValue='';}});
action(async()=>{await configureEntry();try{const data=await api('/api/me');if(data.reviewer)await enter(data.reviewer,data.local);}catch(error){if(error.status!==401)throw error;if(entryMode!=='token'){loginView();return;}try{const local=await api('/api/local-login',{});await enter(local.reviewer,true);}catch(e){if(e.status!==404)throw e;loginView();}}});
setInterval(poll,3000);

// The task selector owns case changes. A loaded WebGL world acknowledges its session.
async function watchBrowserFrame(frame, session){
 const task=state.tasks.find(t=>t.id===session.task_id),loadId=new URL(session.stream_url,location.href).searchParams.get('load_id');
 const current=()=>frame.isConnected&&state.session?.id===session.id&&state.session?.stream_url===session.stream_url;
 const started=Date.now();let preparedDocument=null;
 while(current()&&Date.now()-started<240000){
  try{
   const win=frame.contentWindow,doc=frame.contentDocument;
   if(doc&&doc!==preparedDocument&&win.location.pathname.startsWith('/threejs/')){
    preparedDocument=doc;
    // Keep pointer capture within the embedded game.
    doc.addEventListener('keydown',event=>{
     if(event.code==='Escape'&&doc.pointerLockElement){doc.exitPointerLock();}
    },true);
    doc.addEventListener('pointerdown',event=>{if(event.target.closest?.('canvas')){win.focus();}},true);
   }
   if(win?.__initError)throw new Error('The environment could not initialize.');
   const ready=win?.__env?.ready||win?.BenchmarkWorld?.ready;
   if(ready&&new URL(win.location.href).searchParams.get('bug')===task.source_case&&doc.querySelector('canvas')){
    const label=doc.querySelector('.clean-dive-copy strong');if(label)label.textContent=task.environment+' · '+displayTaskId(task);
    const result=await api('/api/sessions/'+session.id+'/browser-ready',{task_id:task.id,load_id:loadId});
    if(current()){setSession(result.session);if(['Loading environment…','Loading next task…'].includes($('notice').textContent))notify('Environment ready.');}
    return;
   }
  }catch(error){
   if(error.status===401||error.status===409)return;
   if(error.message==='The environment could not initialize.')break;
  }
  await new Promise(resolve=>setTimeout(resolve,300));
 }
 if(current()){
  try{const result=await api('/api/sessions/'+session.id+'/browser-failed',{task_id:task.id,load_id:loadId});if(current())setSession(result.session);}catch{}
 }
}

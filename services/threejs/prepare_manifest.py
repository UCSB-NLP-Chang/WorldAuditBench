#!/usr/bin/env python3
"""Stage the review-site task manifest for the envs-2026-09-15 three.js release.

Reads the LIVE manifest (review-service/state/tasks.json), rewrites only the 105 three.js entries (runtime_kind
"browser") and writes staging/tasks.json plus staging/manifest-report.json.  Non-browser entries are copied
byte-for-byte.  Rules (mirroring the Unreal families' conventions):
  * every three.js task gets the new page hash (build_sha256) and a new per-task version hash (sha256);
  * tasks whose behaviour or judging text changed get revision N+1 and NO compatibility aliases (they need a fresh review);
  * unchanged tasks keep their revision and receive a review_compatible_versions alias of the previous exact
    (revision, sha256, build_sha256) tuple, so existing accepted reviews stay valid;
  * JS_WT06 (reef hole) is retired: removed from the manifest, historical feedback rows are untouched;
  * rubric / description texts are regenerated from the benchmark's answers (env/configs/*.answers.json) in both languages.
"""
import hashlib, json, pathlib, subprocess, sys

ROOT = pathlib.Path('/home/ubuntu/unreal-auditor')
REPO = pathlib.Path('/home/ubuntu/game-auditing')
RELEASE = pathlib.Path(__file__).resolve().parent
SITE = RELEASE / 'site'
STATE = ROOT / 'review-service/state'
LIVE = pathlib.Path(subprocess.check_output(['systemctl', 'show', 'urban-review-pilot.service', '-p', 'WorkingDirectory', '--value'], text=True).strip())
sys.path.insert(0, str(LIVE))
from browser_runtime import validate_browser_task, SUITES  # noqa: E402

PAGE_OF = {p: f for p, (_, f, _) in SUITES.items()}
# round 3 (2026-09-16, the owner's re-review of the revision-2 tasks): behaviour changed -> revision bump, no alias
REVISED = set()   # 2026-09-16c: page-only change (clean review view), no task behaviour / text changes
RETIRED = set()   # nothing retired in this publication (WT03/WT13/WL13 already gone since envs-2026-09-16b)
RENAMED = {'AF11': 'x-ray car', 'AF17': 'street lamp casts no shadow', 'CT04': 'double-spawned bench', 'WT12': 'unloaded rock set',
           'WL12': 'unloaded boulder', 'WL13': 'tree position resets'}
PUBLISHED_ON = '2026-09-16'
CONTENT_UPDATE = {}   # no revised tasks; existing notes are carried forward with refreshed versions
ZH = {  # Chinese versions of the regenerated "where" texts (criteria = 确认以下现象可复现：...)
    'SP02': '一个花盆以约65度倾倒并有一半陷入地面——盆体下半部、一侧盆沿和部分植物在地板以下，另一半斜着露在地板上方，而其他相同的花盆都直立在地面上。',
    'SP03': '八个相同的地面花盆中有一个接近其他花盆的三倍大——高到胸口、一米多宽，立在大厅里，旁边是只到膝盖的同款花盆。',
    'SP15': '侧廊东北角（最后一幅帷幔后面）堆着一堆复制出来的石花盆、花坛和吊炉：花盆互相倾斜穿插，一个侧躺在堆顶，吊炉连着链条倒在地上——重复生成的真实道具挤成一堆（生成失败）。',
    'HS02': '三把相同的厨房吧台凳中有一把以约35度倾倒并陷入地板——凳腿在地板以下，只有倾斜的凳面露在地面上方，而旁边两把凳子都直立在地上。',
    'HS10': '客厅沙发从电视一侧看正常，但绕到沙发背后（沙发靠背与窗户墙之间的空隙，仍在房间内）看时会消失；回到沙发正面它又出现。',
    'WT03': '在礁石中央巡游的三条大尖吻鲈中有一条巨大——约为另外两条相同鱼的六倍，将近六米长，比它游过的巨石还长。',
    'WT04': '出生点西侧（从出生点看在左边）的大块苔藓岩石组被生成了两次——第二份完全相同的岩石组偏移并旋转后嵌在第一份里，相同的岩石形状互相穿插。',
    'WT05': '出生点北侧几米处有一道横跨整条沙道的隐形屏障，什么都看不见却把潜水员挡住。',
    'WT10': '礁石中央东侧的深色岩石（从出生点向北游时在右手边，约一个潜水员长）从南面看得见，但一旦从它的北面看过去就完全消失。',
    'WT12': '游到出生点西侧的大块苔藓岩石组（长着珊瑚的大块深色岩石，从出生点看在左边）附近再游开，整组岩石连同上面的珊瑚会被卸载——回来时已不见，原地只剩一片空沙地。',
    'WT13': '出生点沙道旁的巨石（出生时在右手边）会换边：从出生点向北游到礁石中央（超过约12米）再回来，它就站在沙道左侧、离原位约8米的地方；再离开一次回来，它又回到右边。',
    'WT15': '出生点北侧不远的开阔沙地上，九个完全相同、朝向也完全一样的鹿角珊瑚副本紧紧叠成一堆，互相穿插（生成失败）。',
    'AF02': '发电机旁（出生点西侧）的工具车以约45度倾倒并陷入柏油路面——下半截连轮子都在地面以下，路面直接从车身中间穿过。',
    'AF05': '北侧护栏排以北约8米（出生点以北约16米）有一道横跨整条跑道的隐形屏障，什么都看不见却把你挡住。',
    'AF06': '出生点正前方（北侧）约4米、跑道中线上、北侧护栏排之前的一处，你会直接穿过看似坚实的柏油路面掉进黑暗，然后重生。',
    'AF10': '北侧护栏排（出生点以北8米那一排）从西端数第二个护栏，从南面（出生点一侧）看得见，从它北面看却完全消失。',
    'AF11': '停在出生点南侧石门旁的红色轿车会透过前方一切物体显示出来——被石门柱、护栏和箱子挡住时依然完整可见。',
    'AF15': '出生点东南方几米的开阔柏油路面上，九个油桶、箱子和油壶叠成结实的一堆，互相穿插（生成失败）。',
    'AF17': '出生点东侧的路灯（北侧护栏排东端旁那盏）在柏油路面上完全没有影子，而跑道西侧同款路灯和其他道具都投下长长的影子。',
    'WL01': '紧挨出生点的大巨石（在出生点转身：它在你身后偏右几米处）悬浮在草地上方约3米，底下是空的。',
    'WL02': '出生点西侧约12米的高大松树以约35度倾倒并陷入地面——树干扎进草地，下层树枝刺穿草皮，而其他树都直立在地面上。',
    'WL04': '紧挨出生点的大巨石（出生时在你身后偏右）被生成了两次——第二块完全相同的巨石偏移并旋转后嵌在第一块里，两块岩石互相穿插。',
    'WL08': '出生点东北方坡上的一丛灌木（约20米远，就在那面坡上大巨石的下方）在原地剧烈抖动（物理抖动），而不是像其他灌木那样轻轻摇摆。',
    'WL09': '出生点东北方坡上的大岩石（约25米远）呈现均匀的亮洋红色，缺少应有的岩石纹理与质感。',
    'WL10': '出生点东北方坡上的大巨石（约25米远）从出生点一侧（南面）看得见，从它北面（上坡一侧）看却完全消失。',
    'WL11': '出生点东北方坡上的大巨石（约25米远）会透过前方一切物体显示出来——隔着树木、灌木甚至山坡本身仍然可见。',
    'WL12': '紧挨出生点的大巨石（出生时在你身后偏右）在你走开超过约15米后会被卸载——回到出生点时它已不见，原地只剩草地。',
    'WL13': '出生点西侧约12米的高大松树不会待在原地：走开超过约20米（比如向北走上草地）再回来，它比原来北移了约10米；再离开一次回来，它又回到原位。',
    'WL14': '出生点西侧约12米的高大松树，只要你离它超过约16米就显示为一个粗糙的平面着色绿色圆锥，走近后才突然变成有细节的树。',
    'WL15': '出生点西南方、靠近水边的开阔草地上，九块完全相同的小巨石紧紧挤成一堆、互相穿插（生成失败）。',
    'WL17': '出生点西北方（约20米远，坡上）的大圆冠树上下颠倒——树冠贴在地面上，光秃秃的树干从树冠顶部直直伸向天空。',
    'CT02': '西侧花园的石头野餐桌以约40度倾倒并陷入草坪——半张桌面和一侧长凳在草皮以下，另一半翘在空中。',
    'CT04': '西侧花园石桌东边的花园长凳被生成了两次——第二把完全相同的长凳偏移并旋转后嵌在第一把里，座板和凳腿互相穿插。',
    'CT13': '立在小路西侧池塘里的高灯柱，每次走开再回来都在不同位置（位置重置，跳动约2.5米）。',
    'CT16': '小屋前门整个缺失——门框里是空的，能直接看到屋内（没有门也没有门把手），但门的碰撞体仍在，一道看不见的屏障挡住你，无法走进去。',
    'CT17': '整个场景大约每秒在白天和黑夜之间闪烁切换——瞬间切换、来回跳变，完全不像正常那种半分钟一次、带平滑过渡的缓慢昼夜循环。',
}
# WL09 is a "material anomaly" case whose rubric is authored (not the answer text); its previous text named the wrong boulder
MATERIAL_EN = {'WL09': 'The large boulder up the slope north-east of the starting point (about 25 m away) has a uniform bright magenta surface without the expected rock pattern and surface character.'}
SCENE_EXTRA = {  # scene facts the reviewers asked for (SP07: drapes are solid here; CT17: the normal day cycle)
    'SP': ('柱间悬挂的帷幔在这个世界里是实体屏障，无法穿过。', 'The drapes hanging between the columns are solid barriers in this world; they cannot be walked through.'),
    'CT': ('场景的时段（日出、白天、日落、夜晚）大约每半分钟自动切换一次，切换时有两秒的平滑过渡。', 'The time of day (sunrise, day, sunset, night) changes by itself about every half minute, with a smooth two-second cross-fade.'),
}


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    live = json.loads((STATE / 'tasks.json').read_text())
    tasks = live['tasks']
    page_sha = {f: sha(SITE / f) for f in set(PAGE_OF.values())}
    out, report = [], {'revised': [], 'aliased': [], 'retired': [], 'text_changed': [], 'title_changed': []}
    for t in tasks:
        if t.get('runtime_kind') != 'browser':
            out.append(t); continue
        suffix = t['id'][3:]               # SP02
        prefix, num = suffix[:2], suffix[2:]
        if suffix in RETIRED:
            report['retired'].append(t['id']); continue
        e = json.loads(json.dumps(t, ensure_ascii=False))   # deep copy
        src = e['source_case']
        page = PAGE_OF[prefix]
        old = (e['revision'], e['sha256'], e['build_sha256'])
        e['build_sha256'] = page_sha[page]
        e['package_id'] = 'game-auditing/envs-2026-09-16c'
        if suffix in REVISED:
            e['revision'] = old[0] + 1
            e.pop('review_compatible_versions', None)
            report['revised'].append(t['id'])
        else:
            aliases = [v for v in e.get('review_compatible_versions', []) if (v['revision'], v['sha256'], v['build_sha256']) != old]
            aliases.append({'revision': old[0], 'sha256': old[1], 'build_sha256': old[2]})
            e['review_compatible_versions'] = aliases
            report['aliased'].append(t['id'])
        e['sha256'] = hashlib.sha256(f"{e['build_sha256']}:{src}:r{e['revision']}".encode()).hexdigest()
        e['case_id'] = f"{t['id']}-R{e['revision']:02d}"
        version = {k: e[k] for k in ('revision', 'sha256', 'build_sha256')}
        if suffix in CONTENT_UPDATE:
            zh_u, en_u = CONTENT_UPDATE[suffix]
            e['content_update'] = {'version': version, 'published_on': PUBLISHED_ON, 'timezone': 'America/Los_Angeles', 'summary_i18n': {'zh': zh_u, 'en': en_u}, 'publication': 'threejs-envs-20260916-v1'}
        elif e.get('content_update'):
            e['content_update'] = dict(e['content_update'], version=version)   # keep the round-2 note, point it at the rebuilt page
        # ---- texts from the benchmark answers
        ans_p = REPO / 'env' / 'configs' / f'{src}.answers.json'
        if e['case_type'] != 'baseline' and ans_p.exists():
            ans = json.loads(ans_p.read_text())[0]
            where, name = ans['where'], ans['name']
            zh = ZH.get(suffix)
            custom = suffix in MATERIAL_EN or not e['rubrics_i18n']['en']['criteria'].startswith('Confirm that the following is reproducible: ')
            if custom:
                if suffix in MATERIAL_EN:   # re-authored material-anomaly rubric
                    en_desc, zh_desc = MATERIAL_EN[suffix], zh
                    e['description'] = en_desc
                    e['description_i18n'] = {'zh': zh_desc, 'en': en_desc}
                    e['rubrics_i18n']['en']['criteria'] = en_desc; e['rubrics_i18n']['zh']['criteria'] = zh_desc
                    e['rubrics'] = zh_desc + '\n' + en_desc
                    report['text_changed'].append(t['id'])
                # other authored material rubrics (SP09, HS09, WT09, AF09, CT09) are kept as authored
            else:
                if e['description_i18n']['en'] != where or (zh and e['description_i18n']['zh'] != zh):
                    if zh is None: raise SystemExit(f'{t["id"]}: answer text changed but no Chinese text provided')
                    e['description'] = where
                    e['description_i18n'] = {'zh': zh, 'en': where}
                    e['rubrics_i18n']['en']['criteria'] = 'Confirm that the following is reproducible: ' + where
                    e['rubrics_i18n']['zh']['criteria'] = '确认以下现象可复现：' + zh
                    e['rubrics'] = zh + '\n' + where   # combined field = zh description + en answer text (existing convention)
                    report['text_changed'].append(t['id'])
            if suffix in RENAMED and e.get('title') != RENAMED[suffix]:
                e['title'] = RENAMED[suffix]; e['kind'] = name; report['title_changed'].append(t['id'])
        if prefix in SCENE_EXTRA:
            zh_x, en_x = SCENE_EXTRA[prefix]
            if en_x not in e['scene_i18n']['en']:
                e['scene_i18n'] = {'zh': e['scene_i18n']['zh'].rstrip() + zh_x, 'en': e['scene_i18n']['en'].rstrip() + ' ' + en_x}
        validate_browser_task(e)
        out.append(e)
    ids = [t['id'] for t in out]
    assert len(ids) == len(set(ids)), 'duplicate ids'
    staged = dict(live, tasks=out)
    (RELEASE / 'staging/tasks.json').write_text(json.dumps(staged, ensure_ascii=False, indent=2) + '\n')
    # sanity: every non-browser entry byte-identical to the live manifest
    live_other = [t for t in tasks if t.get('runtime_kind') != 'browser']
    new_other = [t for t in out if t.get('runtime_kind') != 'browser']
    assert json.dumps(live_other, sort_keys=True) == json.dumps(new_other, sort_keys=True), 'non-browser entries changed'
    report.update({'live_release': str(LIVE), 'live_tasks_sha256': sha(STATE / 'tasks.json'), 'entries_before': len(tasks), 'entries_after': len(out),
                   'page_sha256': page_sha, 'browser_entries': sum(1 for t in out if t.get('runtime_kind') == 'browser')})
    (RELEASE / 'staging/manifest-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in report.items() if k != 'page_sha256'}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()

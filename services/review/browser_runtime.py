"""Browser-rendered sessions share review records but never acquire GPU slots."""
import json
import re
import secrets
import time
from urllib.parse import parse_qs, urlsplit

SUITES = {
    'SP': ('sponza', '00_sponza_constrained.html', 15),
    'CT': ('cottage', '01_mistwood_cottage_constrained.html', 17),
    'AF': ('airfield', '03_sketchbook_airfield_constrained.html', 18),
    'HS': ('house', '09_sims_house_builder_constrained.html', 15),
    'WT': ('reef', '10_beautiful_water_clean_constrained.html', 17),
    'WL': ('wilderness', '13_beyond_fable_wilderness_constrained.html', 17),
}


def is_browser(task):
    return task.get('runtime_kind') == 'browser'


def validate_browser_task(task):
    match = re.fullmatch(r'JS_(SP|CT|AF|HS|WT|WL)(\d{2})', task['id'])
    if not match:
        raise ValueError('Invalid browser task ID')
    prefix, number = match.groups()
    family, filename, maximum = SUITES[prefix]
    source = task.get('source_case', '')
    if int(number) > maximum or not re.fullmatch(prefix.lower() + number + r'-[a-z0-9]+', source):
        raise ValueError('Invalid browser case')
    if (number == '00') != (task.get('case_type') == 'baseline'):
        raise ValueError('Invalid browser baseline')
    if task.get('family') != 'threejs_' + family or task['map'] != f'/threejs/{filename}?bug={source}&noui=1&seed=5':
        raise ValueError('Invalid browser environment URL')
    if type(task['revision']) != int or task['revision'] < 1:
        raise ValueError('Invalid browser revision')
    for key in ('sha256', 'build_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', task.get(key, '')):
            raise ValueError('Invalid browser content hash')
    for lang in ('zh', 'en'):
        for key in ('expected', 'steps', 'criteria'):
            if not isinstance(task.get('rubrics_i18n', {}).get(lang, {}).get(key), str) or not task['rubrics_i18n'][lang][key].strip():
                raise ValueError('Incomplete browser rubric')


class BrowserSessions:
    def browser_task(self, row):
        return is_browser(self.tasks[row['task_id']])

    def prepare_browser(self, sid, task):
        url = task['map'] + '&load_id=' + secrets.token_hex(16)
        self.db.execute("UPDATE sessions SET status='starting',slot=NULL,stream_url=?,error=NULL WHERE id=?", (url, sid))
        self.event(sid, 'browser_loading')

    def browser_report(self, sid, user, data, failed=False):
        with self.lock:
            row = self.owned(sid, user)
            if not self.browser_task(row) or row['status'] not in ('starting', 'ready'):
                raise self.problem_type(409, 'Browser session is not loading')
            load_id = parse_qs(urlsplit(row['stream_url']).query).get('load_id', [''])[0]
            if data.get('task_id') != row['task_id'] or data.get('load_id') != load_id:
                raise self.problem_type(409, 'The loaded page belongs to a different task or attempt')
            if failed:
                self.db.execute("UPDATE sessions SET status='failed',stream_url=NULL,error='Browser could not load the environment. Start again.' WHERE id=?", (sid,))
                self.event(sid, 'browser_failed')
            elif row['status'] == 'starting':
                self.db.execute("UPDATE sessions SET status='ready',error=NULL WHERE id=?", (sid,))
                self.event(sid, 'runtime_ready')
            self.db.commit()
            return self.public(self.owned(sid, user))

    def switch_browser(self, old, user, target):
        new_id, now = secrets.token_hex(16), time.time()
        self.db.execute("UPDATE sessions SET status='closed',slot=NULL,stream_url=NULL WHERE id=?", (old['id'],))
        self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (new_id,user['owner'],user['reviewer'],target['id'],target['revision'],target['map'],target['sha256'],target['build_sha256'],self.mode,'starting',None,now,now,None,None,json.dumps(self.case_fields(target),ensure_ascii=False),new_id))
        self.prepare_browser(new_id, target)
        self.event(old['id'], 'task_switched', new_id)
        self.db.commit()
        return self.public(self.owned(new_id, user))

    def tick_browser(self, row, now):
        with self.lock:
            if row['status'] == 'starting':
                since = self.db.execute("SELECT MAX(created) FROM events WHERE session_id=? AND event='browser_loading'", (row['id'],)).fetchone()[0]
                if now - (since or row['created']) > 300:
                    self.db.execute("UPDATE sessions SET status='failed',stream_url=NULL,error='Browser loading timed out. Start again.' WHERE id=? AND status='starting'", (row['id'],))
                    self.db.commit()

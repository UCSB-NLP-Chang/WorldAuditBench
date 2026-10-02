"""Keep environment grouping; sort every task surface by the canonical taxonomy."""
from pathlib import Path
import re,sys

def patch(stage):
    path=Path(stage)/'static/app.js'
    text=path.read_text()
    if 'const subtypeOrder=taxonomyDefinition.categories.flatMap(category=>category.subcategories.map(sub=>sub.code));' in text:
        return
    pattern=r'^function orderedTasks\(tasks\)\{.*$'
    match=re.search(pattern,text,re.M);assert match,'orderedTasks changed'
    old=match[0]
    assert 'const family=' in old and 'number=t=>' in old
    definitions=old.split('return [...tasks].sort')[0]
    assert definitions.endswith(';')
    replacement=definitions+'''
 const subtypeOrder=taxonomyDefinition.categories.flatMap(category=>category.subcategories.map(sub=>sub.code));
 const typeRank=task=>{if(task.case_type==='baseline')return -1;const code=canonicalTaxonomy(task).code;const rank=subtypeOrder.indexOf(code);return rank<0?subtypeOrder.length:rank;};
 return [...tasks].sort((a,b)=>family(a)-family(b)||typeRank(a)-typeRank(b)||number(a)-number(b)||String(a.id).localeCompare(String(b.id)));
}'''
    path.write_text(text[:match.start()]+replacement+text[match.end():])

if __name__=='__main__':patch(sys.argv[1])

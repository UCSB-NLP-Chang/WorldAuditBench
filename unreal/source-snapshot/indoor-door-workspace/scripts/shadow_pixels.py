from PIL import Image,ImageStat,ImageChops
from pathlib import Path
import json
w=Path('/home/ubuntu/unreal-auditor/indoor-door-workspace');d=w.parent/'indoor-workspace/dist/indoor-door-vase-20260913-v3/rendered-review'
a=Image.open(d/'H09-control.png').convert('L');b=Image.open(d/'H09-bug.png').convert('L')
# Pixel regions on the floor, outside either visible vase body.
regions={'large_vase_shadow':(580,345,660,385),'small_vase_shadow':(790,505,870,545)}
result={}
for n,box in regions.items():
 x=a.crop(box);y=b.crop(box);result[n]=dict(control_mean=ImageStat.Stat(x).mean[0],bug_mean=ImageStat.Stat(y).mean[0],mean_abs_difference=ImageStat.Stat(ImageChops.difference(x,y)).mean[0])
assert result['large_vase_shadow']['bug_mean']-result['large_vase_shadow']['control_mean']>30,result
assert result['small_vase_shadow']['mean_abs_difference']<8,result
result['result']='PASS';(w/'out/shadow-pixels.json').write_text(json.dumps(result,indent=2));print(result)

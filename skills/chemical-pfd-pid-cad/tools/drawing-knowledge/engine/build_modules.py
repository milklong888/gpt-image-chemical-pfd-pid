from pathlib import Path
import json,html
from knowledge import read,write,MODULES
from portable_config import data_root
R=data_root()
FIELDS={
 'common':['项目/图号/版次/阶段/图例约定','采用标准编号与版本','图种与关联表/跨图定位','单位、工况和有效来源','文字/线宽/比例与打印可读性'],
 'tower':['真实塔型和内件类型','设备位号/名称与上游表一致','进料、回流、侧线、塔顶与塔釜真实接口','实际塔板/填料段信息（有依据时）','冷凝/回流罐/再沸器的已定边界','压力/库存/能量/质量测点及操纵量','管口表及需表达的启停/排放/取样接口'],
 'heat_exchanger':['功能、类型及位号','冷热两侧边界与真实管口','介质与流向','设计/操作条件和热负荷的来源','隔离/放空/排净/控制的项目依据'],
 'reactor':['反应器类型/反应与相态依据','进出料/循环/换热接口','热移除与约束的控制意图','测量位置、停留/库存和操纵自由度','搅拌或内件/催化剂的真实配置'],
 'vessel':['类型、位号与服务','液相/气相/排液等真实接口','液位/压力的控制依据','关联设备与去向','设备条件表和已定保护边界'],
 'pump_compressor':['泵/压缩机真实类型和驱动','吸入口/排出口及流向','安装备用的事实','最小流量/防喘振/密封辅助系统（有项目依据）','控制与联锁按实际设计'],
 'piping':['线号、DN、管道等级/材料和压力等级关系','物流/公用工程代码','连接/交叉与跨图去向','阀类/尺寸、保温/伴热等条件项','真实端点、全长障碍与重叠检查'],
 'instrumentation':['仪表位号和功能','测点真实物理对象','控制目标、MV、动作及信号制式','串级SP、覆盖/选择器的明确终点','设定/报警/联锁值、失效位的批准依据','配套阀与工艺阀供应边界']}
def main():
 kb=read(R/'corpus/knowledge.json'); lookup={n['id']:n for n in kb['nodes']};summary=[]
 for m in MODULES:
  cards=[n for n in kb['nodes'] if m in n.get('modules',[]) and (n['kind']=='Requirement' or n['status']=='reviewed_case')]
  sources=[n for n in kb['nodes'] if m in n.get('modules',[]) and n['kind'] in ['Source','StandardVersion','SymbolRepresentation']]
  content={'module':m,'trigger_terms':MODULES[m],'requirement_ids':[n['id'] for n in cards if n['kind']=='Requirement'],'case_pattern_ids':[n['id'] for n in cards if n['kind']=='CasePattern'],'source_candidate_ids':[n['id'] for n in sources],'fields_to_resolve':FIELDS[m],'conditions':'Field checklist triggers investigation; it does not impose equipment, controls or parameter values. Historical requirements require project-version adoption.','source_of_truth':'corpus/knowledge.json','geometry_checks':['exact endpoint and transformed outward normal','whole-line penetration including first/last segment','same-width nozzle and connected line','cross-layer collinear overlap','redundant bends and print readability'],'rebuild_required_after_source_change':True}
  write(R/'modules'/m/'module.json',content)
  lines=['# '+m+' 模块素材','', '## 触发与字段','', '检索词：'+'、'.join(MODULES[m]),'']+['- '+f for f in FIELDS[m]]
  lines+=['','## 直接可读的来源卡','', '下列卡片是权威记录的派生视图；历史要求尚需项目采用，案例不自动成为规则。','']
  for c in cards:
   lines+=['### '+c['label']+' · '+c['id'],'',c.get('text',''),'','适用：'+c.get('condition','按项目范围')+'；例外：'+c.get('exception','未另列，仍须查父条款')+'。','状态：'+c['status']+'；图种：'+','.join(c.get('drawing_kinds',[]))+'。','']
   for eid in c.get('evidence_ids',[]):
    e=lookup[eid];target=e.get('payload_path',e.get('source_path',''));lines.append(f"- [{e['label']}](<{target}>) · {eid} · SHA {e.get('source_sha256','')[:16]}")
   lines.append('')
  lines+=['## 原图例调用','', '设备图例继续使用既有设备知识目录与完整源图元；PID已有核实图例见原生符号manifest。新识别块仍是候选，未核实端口和类型不得直接用于项目。','', '设备条件图和机械图不默认属于PFD/PID图例，缺图例应记录具体缺口。']
  p=R/'modules'/m/'MODULE.md';p.write_text('\n'.join(lines),'utf8')
  summary.append({'module':m,'cards':len(cards),'candidate_sources':len(sources),'path':str(p)})
 write(R/'modules/index.json',summary);print(summary)
if __name__=='__main__':main()

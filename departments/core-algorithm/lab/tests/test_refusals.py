"""0.15.0-refusals: what a department refuses and what it always asks (matrix rows R49, R103, R37)."""
from pathlib import Path
import unittest, sys, json, ipaddress, importlib.util
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kernel.core import State,Kernel,digest
from tools.run_all import pack,scenes
from extensions.asks import answer,open_asks
import extensions.refusals_classes as C
from extensions.refusals_classes import classes_of,screened,prerequisites,unscreened,unruled,CLASSES
from extensions.refusals_narrowing import relaxations,verdict,install_rule,KINDS

DESK=['110_ops_desk','111_requested_actions'];TEAM=['112_servicing_team','113_servicing_standing_rules']
PRACTICE=TEAM+['114_practice_money_movement'];LOOSE=PRACTICE+['115_servicing_loosens'];REVIEW=['116_pack_review','117_review_of_loosening','118_review_of_practice']
def world(names,*more):return State.from_packs([pack(n) for n in names]+list(more))
def extra(id,**fields):return {'schema':'sutra-extension/2','id':id,**fields}
def look(s,execute=True):return Kernel(s).run_standing(execute=execute)['runs'][0]
def ops(r):return [(e['operation'],e['data'].get('predicate') or e['data'].get('method')) for e in r['trace']]
def books(s):   # everything a refused or blocked run may not change (the journal gets its row, and only that)
    return json.dumps({'budget':s.budget,'providers':s.providers,'evidence':s.evidence,'grants':sorted(s.grants),'active_work':s.active_work,'rules':s.rules,'methods':s.methods,'loaded':s.loaded},sort_keys=True)
def m(id,effect,requires=(),**kw):return dict({'id':id,'effect':effect,'requires':list(requires),'provider':'local-provider','grant':'action:'+id,'cost':{'compute':1,'money':0,'attention':0},'action':'simulate_fact','approved':True},**kw)
def ask(id,fact,to='owner'):return m(id,fact,provider='owner-channel',cost={'compute':0,'money':0,'attention':1},action='ask',ask_to=to,question='May it?')
def r(id,head,branches,replaces=None):return dict({'id':id,'head':head,'branches':branches,'approved':True},**({'replaces':replaces} if replaces else {}))
def row(p,t,final=False,**kw):return dict({'predicate':p,'truth':t,'verified':True,'source':'fixture/test','version':'t1'},**({'final':True} if final else {}),**kw)
cmd=lambda text:{'kind':'command','text':text};tool=lambda text:{'kind':'tool','text':text};path=lambda text:{'kind':'path','text':text};host=lambda text:{'kind':'host','text':text}
def named(step,request):return 'screened:%s@req-%s'%(step,digest(request)[:12])   # the name of a screening row, written out here a second time
def asked_for(step,effect,request,rows=True,requires=None):   # a one-step queue, authored through the classifier as pack 111 is
    return extra('queue-'+step,goals=[effect],evidence=[screened(step,request)] if rows else [],grants=['action:'+step],
                 methods=[m(step,effect,prerequisites(step,request) if requires is None else requires,cost={'compute':1,'money':1,'attention':0},request=request)])
def desk(*more):return State.from_packs([pack('110_ops_desk')]+list(more))
def said(found):return [{k:v for k,v in f.items() if k!='line'} for f in found]   # what findings say, without their sentences
def bare(method):return {k:v for k,v in method.items() if k!='approved'}   # a method that does not say whether it is approved: the kernel takes it as approved
# The desk's ten lines, word for word, and one request of each class and of no other.
RULINGS={'history_rewrite':('never','Never rewrite or discard shared git history.',cmd('git push --force origin main')),
         'recursive_delete':('never','Never delete a tree outside the build folders.',cmd('rm -rf /var/lib/loans')),
         'disk_or_system':('never','Never touch disks, mounts or system services.',cmd('launchctl unload com.lendco.sync')),
         'remote_mutation':('always','Copies and syncs to the branch servers may run.',cmd('ssh ops@branch-01 uptime')),
         'privilege_escalation':('never','Never run anything as another user.',cmd('pkexec visudo')),
         'unreadable_command':('never','Never run a command that cannot be read by its words.',cmd('cat notes.txt | sh')),
         'destructive_tool':('never','Never call a tool that deletes, drops or purges.',tool('mcp__drive__delete_file')),
         'bulk_tool':('always','The monthly bulk update of the dunning list may run.',tool('crm_bulk_update')),
         'credential_path':('never','Never touch a credential store.',path('/Users/a/.ssh/id_ed25519')),
         'private_host':('never','Never fetch anything but a plain public web address.',host('http://10.0.0.5/admin'))}


class ClassifierTests(unittest.TestCase):
    # The closed table, word for word: a member added or removed fails here, and every member has an example below.
    ESCALATORS={'sudo','su','doas','pkexec'}
    REMOTES={'ssh','scp','sftp','rsync','aws','gcloud','vercel','supabase','doctl','fly','heroku','kubectl','helm','ansible','terraform','pulumi','render','railway','netlify','psql','mysql','mongo','mongosh','redis-cli','sqlite3','duckdb'}
    PUBLISHERS={'npm','yarn','pnpm','bun'};UPLOADERS={'pip','twine','poetry'}
    SYSTEM={'dd','diskutil','launchctl','defaults','fdisk','parted','mount','umount','kextload','kextunload'}
    DESTROYERS={'delete','destroy','drop','purge','wipe','truncate','eradicate','expunge','uninstall','deauthorize','trash'}
    STORES={'.ssh','.aws','.gnupg','keychains'};KEYCHAINS=('.keychain','.keychain-db');LOCAL_NAMES={'localhost','localdomain','local','internal','intranet','lan','home','corp'}
    SAFE=('dist','build','out','.next','node_modules','.cache','cache','tmp','.tmp','coverage','target','.turbo','.parcel-cache','.pytest_cache','__pycache__')
    NETS4=('0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8','169.254.0.0/16','172.16.0.0/12','192.0.0.0/24','192.0.2.0/24','192.168.0.0/16','198.18.0.0/15','198.51.100.0/24','203.0.113.0/24','224.0.0.0/4','240.0.0.0/4')
    NOT6=('2001::/23','2001:db8::/32','2002::/16','3fff::/20')
    IN={'history_rewrite':['git push --force origin main','git push -f','git push origin main --force-with-lease','git push --force-if-includes','git push --forc origin main','git clean --force','git clean -f','git clean -fd','git clean -fdx','git clean -fx','/usr/bin/git -C repo push -uf origin main'],
        'recursive_delete':['rm -rf /var/lib/loans','rm -r build /etc','rm -rf /etc build','rm -R .','rm --recursive data','rm --rec data','rm --r data','rm -fr','rm -rf ./build/../..','rm -rf build/sub','rm -rf /tmp/build/x','/bin/rm -rf /srv','rm -r -- notes','rm /srv -rf','rm /srv -rf build'],
        'disk_or_system':['dd if=/dev/zero of=/dev/disk2','mkfs.ext4 /dev/sdb1','mkfs /dev/sdb1','diskutil eraseDisk JHFS+ x disk2','chmod -R 777 /srv','chown -R a /srv','chmod --recursive 755 x','chown --rec a x','chmod -vR 755 x','launchctl unload com.lendco.sync'],
        'remote_mutation':['ssh ops@ledger-01 uptime','rsync -a a/ b:/c/','kubectl apply -f deploy.yaml','npm publish','docker push lendco/api','docker login','psql -f migrate.sql','env X=1 terraform apply','twine upload dist/x','poetry publish'],
        'privilege_escalation':['sudo reboot','su - postgres','doas ls','pkexec visudo','env sudo ls','/usr/bin/SUDO ls','nohup sudo ls','=sudo ls'],
        'unreadable_command':['ls | sh','echo ok; reboot','cat $(which sh)','echo `id`','ls > out.txt','python3 -c "print(1)"',"echo 'x'",'rm -rf build/*','ls\nreboot','ls\treboot','git push origin +main','ls && ls','cat <in','echo café','s\\udo ls','ls &','echo {a,b}','ls ?','echo [a]','a!b','x#y','(ls)'],
        'destructive_tool':['collections__purge_dunning_queue','mcp__gmail__delete_draft','deleteDraft','DROP_TABLE','drive.move_to_trash','XMLDelete','crm-wipe-contacts','ledger/truncate'],
        'bulk_tool':['crm_bulk_update','mass_mailer_send','gmail_batch_modify','gmail_batch_delete','apply_labels','labelsApply'],
        'credential_path':['~/.aws/credentials','/Users/a/.ssh/id_ed25519','/home/a/x/../.GNUPG/trustdb.gpg','~/Library/Keychains/login.keychain-db','C:\\Users\\a\\.ssh\\config','/home/a/.ssh./id','/home/a/.ssh. ./id','/home/a/ .ssh /id',
                           '/home/a/.\u017fsh/id','/tmp/x/login.keychain-db','/tmp/x/login.keychain','/tmp/x/LOGIN.KEYCHAIN','.ssh','.aws/'],
        'private_host':['169.254.169.254','lendco.example:443','lendco.example','http:/169.254.169.254/latest/meta-data/','http:\\\\169.254.169.254\\latest','http://lendco.example\\@127.0.0.1/','https://lendco.example/a\\b',
                        'ftp://files.lendco.example/x','file:///etc/passwd','gopher://x.example/','javascript:alert(1)','https://','http:///x','http://?x','http://user@lendco.example/','http://user:pw@lendco.example/',
                        'http://127.0.0.1@lendco.example/','http://lendco.example:/','http://lendco.example:123456/','http://lendco.example:80a/','http://lendco.example:-1/','xhttp://lendco.example/','htp://lendco.example/',
                        'http://localhost:8080/','http://LOCALHOST/','http://ip6-localhost/','http://ip6-loopback/','http://intranet/','http://api.localhost/','http://printer.local/','http://metadata.google.internal/',
                        'http://2130706433/','http://0x7f.0.0.1/','http://010.0.0.1/','http://127.1/','http://1.2.3/','http://256.1.1.1/','http://1.2.3.4.5/','http://00.0.0.0/','http://lendco.example./','http://.lendco.example/',
                        'http://lendco..example/','http://-lendco.example/','http://lendco-.example/','http://lendco.xn--p1ai/','http://lendco.example1/','http://lendco_x.example/','http://lendco.example%2e/',
                        'http://[::1]:8000/','http://[fe80::1%25en0]/','http://[fe80::1]/','http://[fd00::1]/','http://[::ffff:127.0.0.1]/','http://[::]/','http://[::127.0.0.1]/','http://[ff02::1]/','http://[2001:db8::1]/',
                        'http://[2002:7f00:1::1]/','http://[2001::1]/','http://[2001:1ff::1]/','http://[3fff:abc::1]/','http://[64:ff9b::7f00:1]/','http://[1::1]/','http://[4000::1]/','http://[zz]/','http://[::1/','http://[1:2]/','http://[]/','http://[2606:4700::1111]x/']}
    OUT={'command':['python3 reports/due_list.py --month 2026-11','git push origin main','git push --follow-tags','git push --for origin','git status','git clean -n','git commit -a','git fetch --force','rm --verbose notes.txt','rm --force notes.txt',
                    'chmod --reference=a b','chmod --re 755 x','chmod -v 755 x','ls --recursive','rm notes.txt','rm -f notes.txt','rm -rf build','rm -rf ./dist /tmp/cache node_modules/','ls -la','ls -R','npm install',
                    'yarn add x','docker build -t lendco/api .','pip install requests','poetry install','publish notes','upload notes','chmod 644 notes.txt','chown a notes.txt','push notes','X=sudo ls','sudoku play','mkdir -p out'],
         'tool':['createJiraIssue','gmail_create_draft','dropdown_list','batch_get_items','ledger.read_balance','apply_discount','list_labels','undelete_draft','sudo'],
         'path':['reports/due_list.csv','/srv/loans/ssh_notes.md','~/.sshd_config_backup','/home/a/aws/notes.txt','/home/a/keychain.txt','/home/a/.ssh2/id','/home/a/x.ssh/id'],
         'host':['https://api.lendco.example/v1/loans','http://lendco.example','HTTPS://API.LENDCO.EXAMPLE/','https://lendco.example:8443/x?y=1#z','https://lendco.example?x=1','https://lendco.example#top','https://172.32.0.1/','http://11.0.0.1',
                 'http://8.8.8.8:53/','https://[2606:4700::1111]/','https://[2606:4700::1111]:443/x','https://[2001:200::1]/','https://[2a00:1450:4001::200e]/','https://[3ffe::1]/','https://bad.cafe/','https://api.lendco.example/v1/users/a@b','https://a-b.lendco.example/','https://3.lendco.example/','https://1.2.lendco.example/','https://lendco.4.example/']}
    def test_the_table_is_closed_and_every_member_puts_its_request_in_the_class(self):
        self.assertEqual((C.ESCALATORS,C.REMOTES,C.PUBLISHERS,C.UPLOADERS,C.SYSTEM,C.DESTROYERS,C.STORES,C.KEYCHAINS,C.LOCAL_NAMES),
                         (self.ESCALATORS,self.REMOTES,self.PUBLISHERS,self.UPLOADERS,self.SYSTEM,self.DESTROYERS,self.STORES,self.KEYCHAINS,self.LOCAL_NAMES))
        self.assertEqual(([str(n) for n in C.NETS4],str(C.GLOBAL6),[str(n) for n in C.NOT6]),(list(self.NETS4),'2000::/3',list(self.NOT6)))
        self.assertEqual((C.PLAIN.pattern,C.WILD.pattern,C.LABEL.pattern,C.KINDS,C.SOURCE),(r'[A-Za-z0-9 _./=:@,%~-]+',r'[*?\[\]{}$`]',r'[a-z0-9]([a-z0-9-]*[a-z0-9])?',('command','tool','path','host'),'adapter:refusals/classes@1'))
        self.assertEqual(C.SAFE_TREE.pattern,r'(\./|/tmp/)?('+'|'.join(n.replace('.',r'\.') for n in self.SAFE)+')/?')
        self.assertEqual(C.URL.pattern,r'https?://(\[[0-9a-f:.]+\]|[a-z0-9.-]+)(:[0-9]{1,5})?([/?#].*)?')
        self.assertEqual([(c,kind) for c,(kind,_,_) in CLASSES.items()],[('history_rewrite','command'),('recursive_delete','command'),('disk_or_system','command'),('remote_mutation','command'),('privilege_escalation','command'),
                                                                         ('unreadable_command','command'),('destructive_tool','tool'),('bulk_tool','tool'),('credential_path','path'),('private_host','host')])
        self.assertTrue(all(type(what) is str and what for _,what,_ in CLASSES.values()))
        one=lambda request:classes_of(request)
        for w in self.ESCALATORS:self.assertEqual(one(cmd(w+' ls')),['privilege_escalation'],w)
        for w in self.REMOTES:self.assertEqual(one(cmd(w+' x')),['remote_mutation'],w)
        for w in self.PUBLISHERS:self.assertEqual((one(cmd(w+' publish')),one(cmd(w+' install'))),(['remote_mutation'],[]),w)
        for w in self.UPLOADERS:self.assertEqual((one(cmd(w+' upload x')),one(cmd(w+' publish')),one(cmd(w+' install x'))),(['remote_mutation'],['remote_mutation'],[]),w)
        for w in self.SYSTEM:self.assertEqual(one(cmd(w+' x')),['disk_or_system'],w)
        for w in self.DESTROYERS:self.assertEqual(one(tool('crm_'+w+'_contact')),['destructive_tool'],w)
        for w in self.STORES:self.assertEqual((one(path('/Users/a/'+w+'/x')),one(path('/Users/a/'+w.upper()))),(['credential_path'],['credential_path']),w)
        for w in self.LOCAL_NAMES:self.assertEqual((one(host('http://printer.'+w+'/')),one(host('https://'+w+'.example/'))),(['private_host'],[]),w)   # as the last part of a name, not elsewhere in it
        for n in self.SAFE:   # the build folders may go, under ./ or /tmp/ too; anything inside or beside them may not
            self.assertEqual([one(cmd('rm -rf '+p)) for p in (n,'./'+n,'/tmp/'+n,n+'/',n+'/sub','/srv/'+n,n+'x')],[[],[],[],[],['recursive_delete'],['recursive_delete'],['recursive_delete']],n)
        for cidr in self.NETS4:   # both ends of every range are in the class; the addresses just outside are public unless another range holds them
            net=ipaddress.ip_network(cidr);inside=lambda a:any(a in ipaddress.ip_network(c) for c in self.NETS4)
            for a in (net[0],net[-1]):self.assertEqual(one(host('http://%s/'%a)),['private_host'],str(a))
            for a in ([net[0]-1] if int(net[0]) else [])+([net[-1]+1] if int(net[-1])<2**32-1 else []):self.assertEqual(one(host('http://%s/'%a)),['private_host'] if inside(a) else [],str(a))
        for cidr in ('2000::/3',)+self.NOT6:   # IPv6 is public only inside 2000::/3 and outside the three ranges
            net=ipaddress.ip_network(cidr)
            for a,want in ((net[0],cidr!='2000::/3'),(net[-1],cidr!='2000::/3'),(net[0]-1,cidr=='2000::/3'),(net[-1]+1,cidr=='2000::/3')):
                self.assertEqual(one(host('https://[%s]/'%a))==['private_host'],want or any(a in ipaddress.ip_network(c) for c in self.NOT6),str(a))
    def test_a_request_is_put_in_classes_by_its_words(self):
        self.assertEqual(set(self.IN),set(CLASSES))   # every class of the table has its examples here
        for name,texts in self.IN.items():
            for text in texts:self.assertIn(name,classes_of({'kind':CLASSES[name][0],'text':text}),text)
        for kind,texts in self.OUT.items():
            for text in texts:self.assertEqual(classes_of({'kind':kind,'text':text}),[],text)   # an ordinary action has no class
        # A request may be in several classes, in the table's order; a command that is not plain words is still read for the words it shows.
        self.assertEqual(classes_of(cmd('sudo rsync -a loans/ backup:/srv/loans/')),['remote_mutation','privilege_escalation'])
        self.assertEqual(classes_of(cmd('sudo rm -rf /')),['recursive_delete','privilege_escalation'])
        self.assertEqual(classes_of(cmd('echo ok; sudo reboot')),['privilege_escalation','unreadable_command'])
        self.assertEqual(classes_of(cmd('sudo git push -f; rm -rf /; dd; ssh x')),list(CLASSES)[:6])
        self.assertEqual(classes_of(tool('crm_bulk_delete_contacts')),['destructive_tool','bulk_tool'])
        for name,(_,_,request) in RULINGS.items():self.assertEqual(classes_of(request),[name])
    def test_each_class_is_read_in_one_kind_of_request(self):
        # Known limit, pinned: a command is not read for the paths or addresses among its words (the charter's Trust Mode reads a command by its program).
        for text,want in (('cat ~/.aws/credentials',[]),('tar -czf keys.tgz -C.ssh .',[]),('curl http://169.254.169.254/latest/meta-data/',[]),('curl 127.1',[]),('ping localhost',[]),
                          ('scp ~/.ssh/id_ed25519 ops@192.168.1.10:/tmp/',['remote_mutation']),('curl https://api.lendco.example/v1/loans',[])):
            self.assertEqual(classes_of(cmd(text)),want,text)
        # The same words asked for as what they are meet their class; and a tool, a path or a host is not read as a command.
        self.assertEqual((classes_of(path('~/.aws/credentials')),classes_of(host('http://169.254.169.254/latest/meta-data/'))),(['credential_path'],['private_host']))
        self.assertEqual((classes_of(tool('sudo')),classes_of(path('sudo rm -rf /')),classes_of(path('delete_all')),classes_of(tool('rm')),classes_of(host('https://sudo.example/delete'))),([],[],[],[],[]))
        for kind in C.KINDS:   # every class reads one kind, and every kind has a class
            self.assertTrue(any(read_in==kind for read_in,_,_ in CLASSES.values()))
    def test_a_request_of_the_wrong_shape_is_refused_not_waved_through(self):
        for bad in (None,'sudo ls',['command','ls'],{'kind':'command'},{'text':'ls'},{'kind':'shell','text':'ls'},{'kind':'command','text':''},{'kind':'command','text':'   '},{'kind':'command','text':5},
                    {'kind':'command','text':'ls','as':'root'},{'kind':['command'],'text':'ls'},{'kind':'command','text':'x'*2001},{'kind':'tool','text':'delete draft'},{'kind':'tool','text':'purgé'},
                    {'kind':'host','text':'http://a b/'},{'kind':'host','text':'http://a\tb/'},{'kind':'host','text':'http://lendco.exämple/'},{'kind':'path','text':'~/.ssh\x00.txt'},{'kind':'path','text':'a\x7fb'},
                    # a path names one place: with a wildcard or a variable it is refused as a request, so no row is written and nothing unread runs
                    path('~/.a*s/credentials'),path('~/.s?h/id'),path('~/.[s]sh/id'),path('~/{.ssh,x}/id'),path('$HOME/.ssh/id'),path('`pwd`/.ssh')):
            with self.assertRaises(ValueError,msg=repr(bad)):classes_of(bad)
            with self.assertRaises(ValueError,msg=repr(bad)):screened('step@1',bad)
            with self.assertRaises(ValueError,msg=repr(bad)):prerequisites('step@1',bad)
        for bad in (None,'',7):
            with self.assertRaises(ValueError):screened(bad,cmd('ls'))
            with self.assertRaises(ValueError):prerequisites(bad,cmd('ls'))
        self.assertEqual((classes_of(cmd('x'*2000)),classes_of(path('~/notes (old)/a b.txt'))),([],[]))   # at the bound, and a path with spaces and brackets of the round kind
    def test_a_step_is_authored_through_the_classifier_and_the_audit_names_one_that_is_not(self):
        req=cmd('sudo rsync -a loans/ backup:/srv/loans/');got=screened('sync@1',req);name=named('sync@1',req)
        self.assertEqual(got,{'predicate':name,'truth':'TRUE','verified':True,'source':'adapter:refusals/classes@1','version':'req-'+digest(req)[:12],'request':req,'classes':['remote_mutation','privilege_escalation']})
        self.assertEqual(len({name,named('sync@1',cmd('rsync -a loans/ backup:/srv/loans/')),named('sync@2',req),screened('sync@1',cmd('rsync -a loans/ backup:/srv/loans/'))['predicate'],screened('sync@2',req)['predicate']}),3)   # another request or another step, another name
        self.assertEqual(prerequisites('sync@1',req),[name,'may:remote_mutation','may:privilege_escalation'])
        self.assertEqual(prerequisites('export@1',cmd('ls -la')),[named('export@1',cmd('ls -la'))])
        got['request']['text']='ls';self.assertEqual(req,cmd('sudo rsync -a loans/ backup:/srv/loans/'))   # the row holds its own copy of the request
        queue=pack('111_requested_actions');self.assertEqual(unscreened(queue),[])
        for mth in queue['methods']:   # the recorded queue: every step carries its request, its row and exactly the prerequisites its classes need
            self.assertEqual((mth['requires'],[e for e in queue['evidence'] if e['predicate']==named(mth['id'],mth['request'])]),(prerequisites(mth['id'],mth['request']),[screened(mth['id'],mth['request'])]))
        def forged(change):
            q=json.loads(json.dumps(queue));change(q);return unscreened(q)
        first=lambda q:q['methods'][0];own=named('restart-ledger-sync@1',first(queue)['request'])
        self.assertEqual(forged(lambda q:first(q)['requires'].remove('may:privilege_escalation')),['restart-ledger-sync@1: its prerequisites leave out may:privilege_escalation'])
        self.assertEqual(forged(lambda q:first(q).update(requires=[])),['restart-ledger-sync@1: its prerequisites leave out %s, may:privilege_escalation'%own])
        self.assertEqual(forged(lambda q:first(q)['request'].update(text='sudo systemctl stop ledger-sync')),   # the request changed and was not screened again: its row is missing, its own name is not required, another's is
                         ['restart-ledger-sync@1: the pack does not carry the screening row of its request (no row of that name)',
                          'restart-ledger-sync@1: its prerequisites leave out '+named('restart-ledger-sync@1',cmd('sudo systemctl stop ledger-sync')),
                          'restart-ledger-sync@1: it requires the screening of another request (%s)'%own])
        self.assertEqual(forged(lambda q:q['evidence'].pop(0)),['restart-ledger-sync@1: the pack does not carry the screening row of its request (no row of that name)'])
        self.assertEqual(forged(lambda q:q['evidence'][0].update(classes=[])),['restart-ledger-sync@1: the pack does not carry the screening row of its request (another request, version or list of classes)'])   # a row that hides a class
        self.assertEqual(len(forged(lambda q:q['evidence'][0].update(source='anyone'))),1)
        self.assertEqual(forged(lambda q:q['methods'][5]['requires'].append(own)),['export-due-list@1: it requires the screening of another request (%s)'%own])
        self.assertEqual(forged(lambda q:q['methods'][5]['requires'].append('screened:export-due-list@1')),['export-due-list@1: it requires the screening of another request (screened:export-due-list@1)'])
        self.assertIn('its request cannot be read',forged(lambda q:first(q).update(request={'kind':'shell','text':'ls'}))[0])
        self.assertEqual(forged(lambda q:first(q).pop('request')),[])   # a step that carries no request is not a screened step: the audit names it only when asked to cover every step
        self.assertEqual(forged(lambda q:q['methods'].append('not a method')),['a method that is not an object cannot be read'])
        for bad in (None,[],'pack',{'methods':{}},{'evidence':'rows'}):
            with self.assertRaises(ValueError,msg=repr(bad)):unscreened(bad)
        self.assertEqual(unscreened({'methods':[],'evidence':[{'predicate':['x']},{'predicate':{'a':1}},{'no':'name'},'row',None]}),[])   # a row without a name is no screening row; the audit does not stop on it
        self.assertEqual(len(forged(lambda q:q['evidence'].__setitem__(0,{'predicate':[own]}))),1)
        self.assertEqual(len(forged(lambda q:first(q).update(requires=' '.join(first(q)['requires'])))),1)   # prerequisites that are not a list are no prerequisites
        bare=json.loads(json.dumps(queue));bare['methods'][0].pop('request')
        self.assertEqual((unscreened(queue,every=True),unscreened(bare,every=True)),([],['restart-ledger-sync@1: it carries no request, so nothing was screened']))
        self.assertEqual((unscreened(pack('113_servicing_standing_rules'),every=True),len(unscreened(pack('112_servicing_team'),every=True))),([],5))   # a question to a person is not a request; the team's five steps carry none
    def test_the_desk_rules_on_every_class_and_the_audit_names_one_nobody_ruled_on(self):
        d=pack('110_ops_desk')
        self.assertEqual([(e['predicate'],e['tag'],e['line'],e['truth'],e.get('final',False),e['source']) for e in d['evidence']],
                         [('may:'+c,tag,line,'FALSE' if tag=='never' else 'TRUE',tag=='never','owner:lendco/operations') for c,(tag,line,_) in RULINGS.items()])
        self.assertEqual((list(RULINGS),unruled(d),unruled([d,pack('111_requested_actions')]),unruled([d,pack('111_requested_actions'),pack('119_platform_allows_itself')])),(list(CLASSES),[],[],[]))
        without=lambda *cs:dict(d,id='desk-without',evidence=[e for e in d['evidence'] if e['predicate'] not in ['may:'+c for c in cs]])
        self.assertEqual((unruled(without('recursive_delete','bulk_tool')),unruled(extra('empty')),unruled([])),(['recursive_delete','bulk_tool'],list(CLASSES),list(CLASSES)))   # in the table's order
        one=lambda **more:unruled([without('bulk_tool'),extra('more',**more)])
        for rows in ([row('may:bulk_tool','TRUE')],[row('may:bulk_tool','FALSE',final=True)],[row('may:bulk_tool','TRUE',final=True)]):self.assertEqual(one(evidence=rows),[])   # a yes, a no by decision, a yes by decision
        self.assertEqual((one(methods=[ask('ask-owner-bulk@1','may:bulk_tool')]),one(methods=[bare(ask('ask-owner-bulk@1','may:bulk_tool'))])),([],[]))   # a question, also one that does not say it is approved (the kernel takes it as approved)
        for more in (dict(evidence=[row('may:bulk_tool','FALSE')]),                                       # an ordinary no is no refusal
                     dict(evidence=[row('may:bulk_tool','TRUE',depends_on=[{'predicate':'x','version':'1'}])]),   # a yes that does not read
                     dict(evidence=[dict(row('may:bulk_tool','TRUE'),verified=False)]),                    # a row the kernel ignores
                     dict(evidence=[row('may:bulk_tool','TRUE',scope='lendco/platform')]),                # a yes in another scope
                     dict(evidence=[row('may:bulk','TRUE')]),
                     dict(methods=[m('permit-bulk@1','may:bulk_tool')]),                                  # a step that is no question
                     dict(methods=[dict(ask('ask-owner-bulk@1','may:bulk_tool'),approved=False)]),
                     dict(rules=[r('R-BULK@1','may:bulk_tool',[['x']])]),                                 # a rule: it stores no row, and a step's own gate reads stored rows (pinned below)
                     dict(scope='lendco/platform')):                                                      # a pack that moves the scope leaves every ruling behind
            self.assertIn('bulk_tool',one(**more),more)
        self.assertEqual(one(scope='lendco/platform'),list(CLASSES))
        # Why a rule is no ruling: it stores no row. Once the rule holds, a step that requires the permission is planned on the rule's head and stops at
        # its own gate, which reads stored rows: the step does not run and is not paid. While the rule's condition is unknown the look wants evidence, as with no rule at all.
        by_rule=lambda *rows:State.from_packs([without('bulk_tool'),extra('by-rule',rules=[r('R-BULK@1','may:bulk_tool',[['x']])],evidence=list(rows)),asked_for('step@1','step_done',tool('crm_bulk_update'))])
        s=by_rule(row('x','TRUE'));before=books(s);x=look(s)
        self.assertEqual((x['status'],x['actions'],x['model_receipts'],x['pending'],x['stopped']['method'],'may:bulk_tool' in x['stopped']['reason'],books(s)),('STEP_STOPPED',[],[],['step@1'],'step@1',True,before))
        self.assertEqual((look(by_rule(row('x','TRUE')),execute=False)['status'],look(by_rule())['status']),('PLAN_READY','QUERY_EVIDENCE'))
        for bad in (None,'pack',7,(d,),[{'id':'x'}],[extra('b',budget={'money':-1})],[d,'pack']):
            with self.assertRaises(ValueError,msg=repr(bad)):unruled(bad)


class RefusedClassTests(unittest.TestCase):
    WANT=['REFUSED','REFUSED','REFUSED','REFUSED','REFUSED','LOCAL_MODEL_EFFECTS_RECORDED','REFUSED','LOCAL_MODEL_EFFECTS_RECORDED']
    def test_a_refused_class_is_refused_though_grant_slot_and_budget_are_there(self):
        s=world(DESK);queue=pack('111_requested_actions');runs=Kernel(s).run_standing(execute=True)['runs']
        self.assertEqual([x['status'] for x in runs],self.WANT)
        for mth,x in zip(queue['methods'],runs):
            self.assertIn(mth['grant'],s.grants);self.assertGreaterEqual(s.providers[mth['provider']],1)   # nothing else stood in the way
            if x['status']=='REFUSED':
                self.assertEqual((x['work_state'],x['actions'],x['model_receipts'],x['cost'],x['stop_reasons'],s.fact(mth['effect'])['truth']),('blocked',[],[],None,['REFUSED'],'UNKNOWN'))
                self.assertEqual(ops(x)[1:-2],[('METHOD_MATCH',mth['effect']),('RETAIN',named(mth['id'],mth['request']))]+[('RETAIN','may:remote_mutation')]*(mth['id']=='sync-loan-book-as-root@1')
                                 +[('REFUSED',next(p for p in mth['requires'] if s.fact(p)['truth']=='FALSE'))])   # the screening row is read, then the first refused class ends the look
            else:self.assertEqual((x['actions'],len(x['model_receipts']),s.fact(mth['effect'])['truth']),([mth['id']],1,'TRUE'))
        self.assertEqual((s.budget,s.providers),({'compute':8,'money':8,'attention':3},{'local-provider':6}))   # two steps ran and were paid; six cost nothing
        # One refused look on a fresh State: nothing but the journal changes.
        s=world(DESK);before=books(s);x=Kernel(s).resolve('ledger_sync_restarted',execute=True)
        self.assertEqual((x['status'],books(s),[(j['goal'],j['status']) for j in s.event_journal]),('REFUSED',before,[('ledger_sync_restarted','REFUSED')]))
    def test_each_class_meets_the_desk_as_its_ruling_says(self):
        one=lambda request,**kw:look(desk(asked_for('step@1','step_done',request,**kw)))
        for name,(tag,_,request) in RULINGS.items():
            self.assertEqual(one(request)['status'],'REFUSED' if tag=='never' else 'LOCAL_MODEL_EFFECTS_RECORDED',name)
        for request in (cmd('ls -la reports'),tool('ledger.read_balance'),path('reports/due_list.csv'),host('https://api.lendco.example/v1/loans')):   # in no class: an ordinary action of each kind runs
            self.assertEqual(one(request)['status'],'LOCAL_MODEL_EFFECTS_RECORDED',request)
        self.assertEqual(one(cmd('ls -la reports'),rows=False)['status'],'QUERY_EVIDENCE')   # a step whose screening row is missing does not run
    def test_only_the_row_of_exactly_that_request_satisfies_the_step(self):
        req=cmd('ls -la reports');name=named('step@1',req)
        s=desk(asked_for('step@1','step_done',req));k=Kernel(s);k.run_standing(execute=True)
        self.assertEqual((s.fact('step_done')['truth'],s.fact('step_done')['depends_on'],s.budget),('TRUE',[{'predicate':name,'version':'req-'+digest(req)[:12]}],{'compute':9,'money':9,'attention':3}))   # what ran rests on the reading of exactly that request
        # The reading of another request for the same step arrives later, from the adapter itself: it is another fact. No goal rests on it, nothing runs, nothing is paid again.
        late=screened('step@1',cmd('sudo rm -rf /var/lib/loans'));paid=(dict(s.budget),dict(s.providers))
        self.assertEqual((late['classes'],k.on_event(late,execute=True)),(['recursive_delete','privilege_escalation'],{'status':'RECONCILED','event':late,'affected':[],'runs':[]}))
        self.assertEqual(((s.budget,s.providers),s.fact('step_done')['truth'],s.fact('step_done')['depends_on'][0]['predicate'],look(s)['status']),(paid,'TRUE',name,'SUPPORTED_BY_EVIDENCE'))
        # The same reading again: the goal is looked at, supported by what stands, and nothing runs or is paid twice.
        out=k.on_event(screened('step@1',req),execute=True)
        self.assertEqual((out['affected'],[(x['status'],x['actions'],x['model_receipts']) for x in out['runs']],(s.budget,s.providers)),(['step_done'],[('SUPPORTED_BY_EVIDENCE',[],[])],paid))
        # A step whose own row is missing is not armed by the bare step name, by another request's row, or by its own row unverified.
        for other in (row('screened:step@1','TRUE'),late,dict(screened('step@1',req),verified=False),screened('step@2',req)):
            s=desk(asked_for('step@1','step_done',req,rows=False));k=Kernel(s);k.on_event(other,execute=True)
            self.assertEqual((look(s)['status'],s.budget),('QUERY_EVIDENCE',{'compute':10,'money':10,'attention':3}),other['predicate'])
        # Nor does a refused step run on the reading of milder words for it.
        two=cmd('sudo rsync -a loans/ backup:/srv/loans/');s=desk(asked_for('step@1','step_done',two));k=Kernel(s)
        self.assertEqual((k.on_event(screened('step@1',req),execute=True)['affected'],look(s)['status']),([],'REFUSED'))
        # Known limit, pinned: a row is believed by its name. A verified row that carries the screening's name arms the step whoever sent it and whatever it says.
        s=desk(asked_for('step@1','step_done',req,rows=False));k=Kernel(s)
        out=k.on_event({'predicate':name,'truth':'TRUE','verified':True,'source':'anyone','classes':['privilege_escalation']},execute=True)
        self.assertEqual([(x['status'],x['actions']) for x in out['runs']],[('LOCAL_MODEL_EFFECTS_RECORDED',['step@1'])])
        # And a row of that name with another version undoes what rested on the first, as any changed prerequisite does: the step runs and is paid again.
        again=k.on_event({'predicate':name,'truth':'TRUE','verified':True,'source':'anyone','version':'other'},execute=True)
        self.assertEqual(([(x['status'],x['actions']) for x in again['runs']],s.budget),([('LOCAL_MODEL_EFFECTS_RECORDED',['step@1'])],{'compute':8,'money':8,'attention':3}))
    def test_deny_wins(self):
        two=cmd('sudo rsync -a loans/ backup:/srv/loans/');name=named('step@1',two)
        # Over a permitted class: in two classes, one permitted and one refused, in either order of reading.
        for requires in (None,[name,'may:privilege_escalation','may:remote_mutation']):
            s=desk(asked_for('step@1','step_done',two,requires=requires));before=books(s);x=look(s)
            self.assertEqual((x['status'],x['actions'],x['stop_reasons'],books(s)),('REFUSED',[],['REFUSED'],before))
        self.assertEqual(ops(look(desk(asked_for('step@1','step_done',two))))[2:5],[('RETAIN',name),('RETAIN','may:remote_mutation'),('REFUSED','may:privilege_escalation')])
        # Over an allow that arrives later as an ordinary row: it is turned away and journalled, and the look is refused as before.
        s=desk(asked_for('step@1','step_done',two));k=Kernel(s);before=books(s)
        self.assertEqual(k.on_event(row('may:privilege_escalation','TRUE'),execute=True),{'status':'DECISION_STANDS','affected':[],'runs':[]})
        self.assertEqual((books(s),s.event_journal[-1],look(s)['status']),(before,{'status':'DECISION_STANDS','scope':'lendco/operations','predicate':'may:privilege_escalation'},'REFUSED'))
        # Over a method, a grant and a bigger budget that a later pack brings for the refused class (recorded with pack 119, and named by the narrowing check).
        s=world(DESK+['119_platform_allows_itself']);runs=Kernel(s).run_standing(execute=True)['runs']
        self.assertEqual(([x['status'] for x in runs],s.budget,'permit-root@1' in [a for x in runs for a in x['actions']]),(RefusedClassTests.WANT,{'compute':48,'money':48,'attention':3},False))
        later=extra('later',methods=[m('permit@1','may:privilege_escalation')],grants=['action:permit@1'],budget={'compute':99,'money':99})
        x=look(desk(asked_for('step@1','step_done',two),later));self.assertEqual((x['status'],x['actions'],x['model_receipts']),('REFUSED',[],[]))
        # Over a rule a later pack puts on the permission: the kernel reads the decision on a fact before any rule on it, so the rule is never read
        # and the look is refused as before, row for row (the trace of the look without the rule, whole, and no REFINE in it); the refusal still stands on the fact.
        s=desk(asked_for('step@1','step_done',two),extra('later-rule',rules=[r('R-MAY@1','may:privilege_escalation',[[name]])]));before=books(s);x=look(s)
        self.assertEqual((x['status'],x['work_state'],x['actions'],x['model_receipts'],x['stop_reasons'],s.fact('may:privilege_escalation')['truth'],books(s)),('REFUSED','blocked',[],[],['REFUSED'],'FALSE',before))
        self.assertEqual((x['trace'],'REFINE' in [o for o,_ in ops(x)]),(look(desk(asked_for('step@1','step_done',two)))['trace'],False))
        # Over a question: where the permitted class is asked about instead, no question is put for a step that is refused anyway.
        p=pack('110_ops_desk');asking=[dict(p,id='desk-asks',evidence=[e for e in p['evidence'] if e['predicate']!='may:remote_mutation']),
                                       extra('ask-remote',methods=[ask('ask-owner-remote@1','may:remote_mutation')],grants=['action:ask-owner-remote@1'],providers={'owner-channel':1})]
        self.assertEqual(unruled(asking),[])
        s=State.from_packs(asking+[asked_for('step@1','step_done',two)]);x=look(s);self.assertEqual((x['status'],x['model_receipts'],open_asks(s),s.budget['attention']),('REFUSED',[],{},3))
        s=State.from_packs(asking+[asked_for('step@1','step_done',cmd('rsync -a loans/ backup:/srv/loans/'))]);x=look(s)
        self.assertEqual((x['status'],x['actions'],x['pending'],len(open_asks(s)),s.budget['attention']),('WAITING',['ask-owner-remote@1'],['step@1'],1,2))   # the class alone: the desk asks and waits
    def test_a_class_nobody_ruled_on_is_named_by_the_audit_because_it_can_hide_a_refusal(self):
        # Known limit, pinned. The kernel reads a step's prerequisites in order and stops at the first that yields no plan (kernel/core.py, the line
        # `if not partial:break` of the method loop). A desk that leaves a class unruled lets that class, read first, name the look: evidence is
        # wanted, the refusal after it is never read. Nothing runs either way. The recorded desk rules on all ten, and the audit names a desk that does not.
        both=cmd('sudo rm -rf /var/lib/loans');name=named('step@1',both);p=pack('110_ops_desk')
        holey=dict(p,id='desk-with-a-hole',evidence=[e for e in p['evidence'] if e['predicate']!='may:recursive_delete'])
        self.assertEqual((classes_of(both),unruled(p),unruled(holey)),(['recursive_delete','privilege_escalation'],[],['recursive_delete']))
        s=State.from_packs([holey,asked_for('step@1','step_done',both)]);before=books(s);x=look(s)   # the table's order: the unruled class is read first
        self.assertEqual((x['status'],x['stop_reasons'],x['actions'],[o for o,_ in ops(x)],books(s)),('QUERY_EVIDENCE',['QUERY_EVIDENCE'],[],['GOAL_ACCEPTED','METHOD_MATCH','RETAIN','QUERY_EVIDENCE','BLOCK','TERMINAL'],before))
        k=Kernel(s);k.on_event(row('may:recursive_delete','TRUE'));self.assertEqual((look(s)['status'],s.budget),('REFUSED',{'compute':10,'money':10,'attention':3}))   # the evidence it asked for, and it is refused
        s=State.from_packs([holey,asked_for('step@1','step_done',both,requires=[name,'may:privilege_escalation','may:recursive_delete'])]);x=look(s)   # the other order: the refusal is read first
        self.assertEqual((x['status'],x['stop_reasons'],x['actions']),('REFUSED',['REFUSED'],[]))
        for requires in (None,[name,'may:privilege_escalation','may:recursive_delete']):   # the recorded desk: refused in either order
            x=look(desk(asked_for('step@1','step_done',both,requires=requires)));self.assertEqual((x['status'],x['stop_reasons'],x['actions']),('REFUSED',['REFUSED'],[]))
        # The same when a permitted class later reads an ordinary no (no ruling: the audit names it in a pack, nothing names it in an event): no method can
        # make the permission true, the look is named for that, and the refusal after it is not read. Nothing runs.
        two=cmd('sudo rsync -a loans/ backup:/srv/loans/');s=desk(asked_for('step@1','step_done',two));k=Kernel(s);k.on_event(row('may:remote_mutation','FALSE'));x=look(s)
        self.assertEqual((x['status'],x['stop_reasons'],x['actions'],s.budget,unruled([p,extra('no',evidence=[row('may:remote_mutation','FALSE')])])),('METHOD_ABSENT',['METHOD_ABSENT'],[],{'compute':10,'money':10,'attention':3},['remote_mutation']))
    def test_a_class_binds_the_steps_that_require_its_permission(self):
        # Known limit, pinned. The kernel never sees a request: a class binds a step through the permission the step requires. A step written by
        # hand without a request runs at the desk, and so does another step for the effect of a refused one. The audit names both when asked to
        # cover every step; the narrowing check names the second (another way to an effect the parent already serves), not the first (a new fact).
        hand=extra('hand',goals=['root_shell_opened'],grants=['action:open-root-shell@1'],methods=[m('open-root-shell@1','root_shell_opened')])
        self.assertEqual((look(desk(hand))['status'],unscreened(hand),unscreened(hand,every=True),relaxations([pack(n) for n in DESK],hand)),
                         ('LOCAL_MODEL_EFFECTS_RECORDED',[],['open-root-shell@1: it carries no request, so nothing was screened'],[]))
        twin=extra('twin',grants=['action:restart-anyway@1'],methods=[m('restart-anyway@1','ledger_sync_restarted')]);x=look(world(DESK,twin));sync=pack('111_requested_actions')['methods'][0]
        self.assertEqual((x['status'],x['actions'],unscreened(twin,every=True)),('LOCAL_MODEL_EFFECTS_RECORDED',['restart-anyway@1'],['restart-anyway@1: it carries no request, so nothing was screened']))
        self.assertEqual(said(relaxations([pack(n) for n in DESK],twin)),[{'kind':'CONDITION_DROPPED','how':'method','method':'restart-anyway@1','effect':'ledger_sync_restarted','beside':'restart-ledger-sync@1',
                                                                          'dropped':sorted(sync['requires']),'grant':'action:restart-anyway@1','provider':None,'cheaper':['money']}])
    def test_what_lifts_a_refusal(self):
        two=cmd('sudo rsync -a loans/ backup:/srv/loans/')
        # In its scope, only another decision lifts a refusal (the kernel does not ask whose it is); the narrowing check names such a pack.
        lift=extra('lift',evidence=[row('may:privilege_escalation','TRUE',final=True)]);s=desk(asked_for('step@1','step_done',two),lift)
        self.assertEqual(look(s)['status'],'LOCAL_MODEL_EFFECTS_RECORDED')
        self.assertEqual(said(relaxations([pack('110_ops_desk')],lift)),[{'kind':'REFUSAL_DROPPED','how':'decision','fact':'may:privilege_escalation','scope':'lendco/operations','source':'fixture/test'}])
        # Known limit, pinned: decisions live under one scope string. A later pack that names another scope and brings ordinary rows leaves every
        # refusal behind: all eight steps of the queue run. The narrowing check names the eight refusals that stay behind.
        queue=pack('111_requested_actions');moved=extra('moved',scope='lendco/platform',evidence=queue['evidence']+[row('may:'+c,'TRUE') for c in CLASSES])
        s=world(DESK,moved);runs=Kernel(s).run_standing(execute=True)['runs']
        self.assertEqual(([x['status'] for x in runs],any(e.get('final') for e in moved['evidence']),s.budget),(['LOCAL_MODEL_EFFECTS_RECORDED']*8,False,{'compute':2,'money':2,'attention':3}))
        found=relaxations([pack(n) for n in DESK],moved)
        self.assertEqual(([(f['kind'],f['how'],f['moved_to']) for f in found],sorted(f['fact'] for f in found)),([('REFUSAL_DROPPED','scope','lendco/platform')]*8,sorted('may:'+c for c,(tag,_,_) in RULINGS.items() if tag=='never')))


class StandingRulesTests(unittest.TestCase):
    def test_the_lines_are_the_owners_words(self):
        lines,pick=pack('113_servicing_standing_rules'),pack('114_practice_money_movement')
        self.assertEqual(lines['standing_rules'],[{'tag':'always','line':"Always check the payee's account against the loan book before a refund is paid.",'grant':'action:check-payee-account@1'},
                                                  {'tag':'ask','line':'Ask me first before a refund is paid.','method':'ask-owner-refund@1'},
                                                  {'tag':'never','line':"Never pay a refund to an account that is not the borrower's own.",'decision':'third_party_payout_allowed'}])
        asking=lines['methods'][0]
        self.assertEqual((asking['id'],asking['action'],asking['ask_to'],asking['question'],asking['provider'],lines['providers']),
                         ('ask-owner-refund@1','ask','owner','A refund of an overpaid instalment is due to the borrower. May it be paid?','owner-channel',{'owner-channel':1}))
        # J2 Pro's Money movement pick, two of its lines word for word (sutra_app/library/specs/practice_packs.json), with their function and tag.
        self.assertEqual(pick['practice'],{'id':'money-movement','name':'Money movement','from':'sutra-pro/sutra_app/library/specs/practice_packs.json'})
        self.assertEqual(pick['standing_rules'],[{'function':'identity','tag':'always','line':'Every money effect names its source record (the bank file, a ledger row or a payment reference) before it is judged.','rule':'R-REFUND@2','grant':'action:name-source-record@1'},
                                                 {'function':'coordination','tag':'never','line':'A payment and its reconciliation are never held by the same person or model: one makes, another checks.','decision':'maker_may_reconcile'}])
        self.assertEqual([pack(n)['scope'] for n in LOOSE],['lendco/servicing']*4)   # every pack of the team names its scope: its decisions stand there whatever the load order
        self.assertEqual((pack('112_servicing_team')['providers'],pack('112_servicing_team')['budget']),({'local-provider':6},{'compute':10,'money':10,'attention':3}))
    def test_always_ask_never_in_one_look(self):
        s=world(TEAM);x=look(s);lines={l['tag']:l for l in pack('113_servicing_standing_rules')['standing_rules']}
        self.assertEqual((x['status'],x['work_state'],x['actions'],x['pending'],x['waits'],x['cost']),
                         ('WAITING','waiting',['check-payee-account@1','ask-owner-refund@1'],['pay-to-borrower@1','reconcile-by-maker@1'],['ask-owner-refund@1'],{'compute':1,'money':0,'attention':1}))
        # always: the step holds its grant by the standing-rules pack alone, ran first and asked nobody
        self.assertEqual((lines['always']['grant'],lines['always']['grant'] in pack('113_servicing_standing_rules')['grants'],lines['always']['grant'] in pack('112_servicing_team')['grants']),
                         (s.methods[x['actions'][0]]['grant'],True,False))
        self.assertEqual((x['model_receipts'][0]['method'],x['model_receipts'][0].get('parked'),s.fact('payee_account_checked')['truth']),('check-payee-account@1',None,'TRUE'))
        # ask: a step of kind ask, to the owner, before the work; the payment and its reconciliation are pending and unpaid
        asked=x['model_receipts'][1]
        self.assertEqual((asked['method'],asked['parked'],asked['ask']['to'],asked['ask']['predicate'],asked['ask']['question'],s.methods[lines['ask']['method']]['action'],s.fact('refund_paid')['truth']),
                         ('ask-owner-refund@1',True,'owner','owner_approved_refund','A refund of an overpaid instalment is due to the borrower. May it be paid?','ask','UNKNOWN'))
        self.assertIn('owner_approved_refund',s.methods['pay-to-borrower@1']['requires']);self.assertEqual((s.budget,s.providers),({'compute':9,'money':10,'attention':2},{'local-provider':5,'owner-channel':0}))
        # never: the route by a third party is refused by decision, though it is the cheaper one and its grant is held
        self.assertIn(('REFUSED',lines['never']['decision']),ops(x));self.assertIn('action:pay-to-third-party@1',s.grants)
        self.assertEqual((s.fact('third_party_payout_allowed')['truth'],s.fact('third_party_payout_allowed')['final'],'pay-to-third-party@1' in x['actions']+x['pending']),('FALSE',True,False))
        self.assertLess(s.methods['pay-to-third-party@1']['cost']['money'],s.methods['pay-to-borrower@1']['cost']['money'])
        self.assertEqual(look(State.from_packs([pack(n) for n in reversed(TEAM)]))['status'],'WAITING')   # the owner's pack names its scope, so it may also come first
    def test_without_each_line_the_look_is_another(self):
        # No standing rules at all: the team does not know whether it may pay, and nothing runs.
        s=world(TEAM[:1]);before=books(s);x=look(s);self.assertEqual((x['status'],x['actions'],books(s)),('QUERY_EVIDENCE',[],before))
        # Without the always line's grant the check may not run: authority is among the reasons (the refused route names the run), and nothing runs or is paid.
        s=world(TEAM,extra('stop',revoke_grants=['action:check-payee-account@1']));before=books(s);x=look(s)
        self.assertEqual((x['work_state'],x['actions'],x['model_receipts'],x['stop_reasons'],books(s)),('blocked',[],[],['AUTHORITY_REQUIRED','REFUSED'],before))
        # Without the ask line's question the approval is simply unknown: evidence is wanted, nobody is asked, nothing runs.
        p=pack('113_servicing_standing_rules');s=State.from_packs([pack('112_servicing_team'),dict(p,id='no-ask',methods=[])]);x=look(s)
        self.assertEqual((x['work_state'],x['actions'],x['stop_reasons'],open_asks(s)),('blocked',[],['QUERY_EVIDENCE','REFUSED'],{}))
        # With the never line turned into a yes, the kernel takes the cheaper route by the third party, unasked: the decision is what closed it.
        x=look(State.from_packs([pack('112_servicing_team'),dict(p,id='no-never',evidence=[row('third_party_payout_allowed','TRUE')])]))
        self.assertEqual((x['status'],x['actions']),('LOCAL_MODEL_EFFECTS_RECORDED',['pay-to-third-party@1','reconcile-by-maker@1']))
    def test_a_line_binds_the_steps_that_are_written_around_it(self):
        # Known limit, pinned. A line is a grant, a question or a decision: it binds the steps that require its fact or hold its grant. Pack 112's
        # steps are written that way. Over a team whose steps are not, the same pack 113 changes nothing: the refund goes to the third party,
        # unasked and unchecked, and the narrowing check has nothing to name.
        mm=lambda i,e,req,c:m(i,e,req,cost=c)
        plain_team=extra('plain-team',scope='lendco/servicing',goals=['refund_settled'],rules=[r('R@1','refund_settled',[['refund_paid','payment_reconciled']])],evidence=[row('refund_due','TRUE')],providers={'local-provider':6},
                         grants=['action:pay-to-borrower@1','action:pay-to-third-party@1','action:reconcile@1'],
                         methods=[mm('pay-to-borrower@1','refund_paid',['refund_due'],{'compute':1,'money':2,'attention':0}),mm('pay-to-third-party@1','refund_paid',['refund_due'],{'compute':1,'money':1,'attention':0}),
                                  mm('reconcile@1','payment_reconciled',['refund_paid'],{'compute':1,'money':0,'attention':0})])
        s=State.from_packs([plain_team,pack('113_servicing_standing_rules')]);x=look(s)
        self.assertEqual((x['actions'],open_asks(s),relaxations([plain_team],pack('113_servicing_standing_rules'))),(['pay-to-third-party@1','reconcile@1'],{},[]))
    def test_the_owners_answer_decides_and_no_rule_method_or_row_overturns_the_never(self):
        s=world(TEAM);k=Kernel(s);x=k.run_standing(execute=True)['runs'][0];receipt=x['model_receipts'][-1]
        with self.assertRaises(ValueError):answer(k,receipt,'TRUE','team-lead',execute=True)   # only the party that was asked answers (0.8.0)
        yes=answer(k,receipt,'TRUE','owner',execute=True)['runs'][0]
        self.assertEqual((yes['status'],yes['actions'],s.fact('refund_paid')['truth'],open_asks(s)),('LOCAL_MODEL_EFFECTS_RECORDED',['pay-to-borrower@1','reconcile-by-maker@1'],'TRUE',{}))
        s=world(TEAM);k=Kernel(s);x=k.run_standing(execute=True)['runs'][0]
        no=answer(k,x['model_receipts'][-1],'FALSE','owner',execute=True)['runs'][0]
        self.assertEqual((no['status'],no['actions'],no['stop_reasons'],s.fact('refund_paid')['truth']),('REFUSED',[],['REFUSED'],'UNKNOWN'))   # no by the owner: nothing is paid, by either route
        self.assertEqual([p for o,p in ops(no) if o=='REFUSED'],['owner_approved_refund','third_party_payout_allowed'])
        # The never line against everything a later pack or event may bring that is not a decision.
        later=extra('later',rules=[r('R-THIRD@1','third_party_payout_allowed',[['refund_due']])],methods=[m('unlock-third-party@1','third_party_payout_allowed')],grants=['action:unlock-third-party@1'])
        s=world(TEAM,later);k=Kernel(s);x=k.run_standing(execute=True)['runs'][0]
        self.assertEqual((x['status'],x['pending'],'unlock-third-party@1' in x['actions']+x['pending']),('WAITING',['pay-to-borrower@1','reconcile-by-maker@1'],False))
        self.assertEqual((k.on_event(row('third_party_payout_allowed','TRUE'),execute=True)['status'],s.fact('third_party_payout_allowed')['truth']),('DECISION_STANDS','FALSE'))
    def test_a_practice_pick_only_adds(self):
        team,practice=look(world(TEAM)),look(world(PRACTICE));p=pack('114_practice_money_movement')
        # The always line is a duty: one more condition on the rule, met by a step whose grant the pick holds; it runs first and asks nobody.
        self.assertEqual((practice['status'],practice['actions'],practice['pending']),('WAITING',['name-source-record@1']+team['actions'],['pay-to-borrower@1','reconcile-by-checker@1']))
        self.assertEqual((p['rules'][0]['replaces'],set(p['rules'][0]['branches'][0])-set(pack('112_servicing_team')['rules'][0]['branches'][0]),p['grants']),('R-REFUND@1',{'source_record_named'},['action:name-source-record@1']))
        # The never line closes the cheaper reconciliation by the same holder: the plan takes the other holder and costs one more.
        self.assertIn(('REFUSED','maker_may_reconcile'),ops(practice));self.assertEqual((team['pending'][-1],practice['pending'][-1]),('reconcile-by-maker@1','reconcile-by-checker@1'))
        s=world(PRACTICE);k=Kernel(s);x=k.run_standing(execute=True)['runs'][0];yes=answer(k,x['model_receipts'][-1],'TRUE','owner',execute=True)['runs'][0]
        self.assertEqual((yes['status'],yes['actions'],yes['cost'],s.budget,s.providers),('LOCAL_MODEL_EFFECTS_RECORDED',['pay-to-borrower@1','reconcile-by-checker@1'],{'compute':3,'money':2,'attention':0},{'compute':5,'money':8,'attention':2},{'local-provider':2,'owner-channel':0}))
        self.assertEqual(relaxations([pack(n) for n in TEAM],p),[])   # and the narrowing check finds nothing to name


class NarrowingTests(unittest.TestCase):
    WAYS={('CONDITION_DROPPED','rule'),('CONDITION_DROPPED','method'),('CONDITION_DROPPED','shadow'),('CONDITION_DROPPED','derived'),('REFUSAL_DROPPED','decision'),('REFUSAL_DROPPED','scope'),('REFUSAL_DROPPED','grant'),
          ('REFUSAL_DROPPED','looser'),('ASK_DROPPED','answer'),('ASK_DROPPED','method'),('ASK_DROPPED','rule'),('CEILING_RAISED','budget'),('CEILING_RAISED','provider')}   # the thirteen ways, a closed list
    BORROWER=dict(grant='action:pay-to-borrower@1',cost={'compute':1,'money':2,'attention':0});KEPT=['payee_account_checked','owner_approved_refund']   # the grant, the cost and the prerequisites of the parent's way to pay the borrower
    def setUp(self):self.parents=[pack(n) for n in PRACTICE]
    def test_a_child_that_only_narrows_gets_no_finding(self):
        for child in (extra('n1',rules=[r('R-REFUND@3','refund_settled',[['source_record_named','refund_paid','payment_reconciled','receipt_filed']],'R-REFUND@2')]),   # one more condition
                      extra('n2',evidence=[row('weekend_payout_allowed','FALSE',final=True)]),                                                                          # one more refusal
                      extra('n3',methods=[ask('ask-owner-large@1','owner_approved_large_refund')],grants=['action:ask-owner-large@1']),                               # one more question
                      extra('n4',methods=[m('file-receipt@1','receipt_filed',['refund_paid'])],grants=['action:file-receipt@1']),                                    # a step for a new fact
                      extra('n5',methods=[m('pay-by-cheque@1','refund_paid',self.KEPT+['cheque_signed'],**self.BORROWER)]),                                          # a new way that keeps an old one whole and asks for more
                      extra('n6',methods=[m('pay-again@1','refund_paid',self.KEPT,**self.BORROWER)]),                                                                 # a new way that is an old one under another name
                      extra('n7',methods=[m('pay-dearer@1','refund_paid',self.KEPT,grant='action:pay-to-borrower@1',cost={'compute':1,'money':3,'attention':1})]),   # and one that costs more
                      extra('n8',budget={'money':5},providers={'local-provider':2},revoke_grants=['action:pay-to-third-party@1']),                                    # lower ceilings, less authority
                      extra('n9',evidence=[row('owner_approved_refund','FALSE',final=True)]),                                                                          # a no where the parent asks
                      extra('n10',evidence=[row('third_party_payout_allowed','TRUE')]),                                                                                 # an ordinary yes on a refused fact: the kernel turns it away
                      extra('n11',scope='lendco/collections',evidence=[row('third_party_payout_allowed','FALSE',final=True),row('maker_may_reconcile','FALSE',final=True)]),   # moves the scope and takes both refusals along
                      extra('n12',rules=[r('R-RECEIPT@1','receipt_filed',[['refund_paid']])]),                                                                         # a rule on a fact nobody named
                      extra('n13',methods=[dict(m('assume-approval@1','owner_approved_refund'),approved=False),dict(m('pay-fast@1','refund_paid'),approved=False)]),   # steps that are not approved are not ways
                      extra('n14',rules=[dict(r('R-REFUND@9','refund_settled',[['refund_paid']]),approved=False)]),                                                   # a rule that is only proposed
                      extra('n15',providers={'side-door':3},methods=[m('file-by-side-door@1','receipt_filed',provider='side-door')],grants=['action:file-by-side-door@1'])):   # a new provider for a new fact
            self.assertEqual(relaxations(self.parents,child),[],child['id'])
        order=[pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission')]   # the lab's own older packs narrow: a rule that adds a condition to one alternative, then to it again
        self.assertEqual((relaxations(order,pack('06_notify')),relaxations(order+[pack('06_notify')],pack('07_survey_gap')),relaxations(order[:2],extra('one-way',rules=[r('R-ORDER@2','order_complete',[['original_delivered']],'R-ORDER@1')]))),([],[],[]))
        self.assertEqual((relaxations(order[:2],order[2]),relaxations(self.parents[0],self.parents[1])),([],[]))   # steps and a question for conditions the parent left to evidence: how packs are layered; one parent may be handed in as it is
    def test_each_way_to_relax_is_named_with_what_it_relaxes(self):
        stopped=self.parents+[extra('stop',revoke_grants=['action:pay-to-third-party@1'])]
        receipt=self.parents+[extra('receipt',rules=[r('R-REFUND@3','refund_settled',[['source_record_named','refund_paid','payment_reconciled','receipt_filed']],'R-REFUND@2')])]   # a condition the parent leaves to evidence
        rule=lambda **f:dict({'kind':'CONDITION_DROPPED','how':'rule','rule':'R-REFUND@3','replaces':'R-REFUND@2','head':'refund_settled','alternative':1},**f)
        way=lambda mid,beside,**f:dict({'kind':'CONDITION_DROPPED','how':'method','method':mid,'effect':'refund_paid','beside':beside,'dropped':[],'grant':None,'provider':None,'cheaper':[]},**f)
        cases=((extra('x1',rules=[r('R-REFUND@3','refund_settled',[['refund_paid','payment_reconciled']],'R-REFUND@2')]),[rule(dropped=['source_record_named'])]),
               (extra('x2',rules=[r('R-REFUND@3','refund_settled',[['source_record_named','refund_paid','payment_reconciled'],['refund_waived']],'R-REFUND@2')]),   # one more alternative is one more way out
                [rule(alternative=2,dropped=['payment_reconciled','refund_paid','source_record_named'])]),
               (extra('x3',rules=[r('R-REFUND@2','refund_settled',[['refund_paid']],'R-REFUND@2')]),[rule(rule='R-REFUND@2',dropped=['payment_reconciled','source_record_named'])]),   # the same id again: the kernel accepts it, the check reads the content
               (extra('x4',methods=[m('pay-fast@1','refund_paid')],grants=['action:pay-fast@1']),[way('pay-fast@1','pay-to-third-party@1',dropped=['third_party_payout_allowed'],grant='action:pay-fast@1',cheaper=['money'])]),
               (extra('x5',methods=[m('pay-again@1','refund_paid',self.KEPT,cost=self.BORROWER['cost'])],grants=['action:pay-again@1']),[way('pay-again@1','pay-to-borrower@1',grant='action:pay-again@1')]),   # the same step under a grant of its own
               (extra('x6',methods=[m('pay-cheap@1','refund_paid',self.KEPT,grant='action:pay-to-borrower@1',cost={'compute':1,'money':0,'attention':0})]),[way('pay-cheap@1','pay-to-borrower@1',cheaper=['money'])]),   # the same step for less
               (extra('x7',providers={'side-door':1},methods=[m('pay-aside@1','refund_paid',self.KEPT,provider='side-door',**self.BORROWER)]),[way('pay-aside@1','pay-to-borrower@1',provider='side-door')]),   # the same step by another provider
               (extra('x8',methods=[m('pay-unchecked@1','refund_paid',['owner_approved_refund'],**self.BORROWER)]),[way('pay-unchecked@1','pay-to-borrower@1',dropped=['payee_account_checked'])]),
               (extra('x8a',methods=[m('pay-free@1','refund_paid',self.KEPT,grant='action:pay-to-borrower@1',cost={'money':2})]),[way('pay-free@1','pay-to-borrower@1',cheaper=['compute'])]),   # a cost that leaves a dimension out costs nothing there
               (extra('x8b',methods=[m('pay-all@1','refund_paid',self.KEPT,grant='action:pay-aside@1',provider='side-door',cost={'compute':1,'money':1,'attention':0})]),   # everything at once
                [way('pay-all@1','pay-to-borrower@1',grant='action:pay-aside@1',provider='side-door',cheaper=['money'])]),
               (extra('x8c',methods=[bare(m('pay-fast@1','refund_paid'))]),[way('pay-fast@1','pay-to-third-party@1',dropped=['third_party_payout_allowed'],grant='action:pay-fast@1',cheaper=['money'])]),   # a step that does not say it is approved is a step
               (extra('x9',rules=[r('R-CHECKED@1','payee_account_checked',[['refund_due']])]),[{'kind':'CONDITION_DROPPED','how':'shadow','rule':'R-CHECKED@1','head':'payee_account_checked','methods':['check-payee-account@1']}]),
               (extra('x10',evidence=[row('third_party_payout_allowed','TRUE',final=True)]),[{'kind':'REFUSAL_DROPPED','how':'decision','fact':'third_party_payout_allowed','scope':'lendco/servicing','source':'fixture/test'}]),
               (extra('x11',scope='lendco/collections'),[{'kind':'REFUSAL_DROPPED','how':'scope','fact':f,'scope':'lendco/servicing','moved_to':'lendco/collections'} for f in ('maker_may_reconcile','third_party_payout_allowed')]),
               (extra('x12',scope='lendco/collections',evidence=[row('third_party_payout_allowed','TRUE',final=True),row('maker_may_reconcile','FALSE',final=True)]),   # a yes by decision in the new scope is no refusal there
                [{'kind':'REFUSAL_DROPPED','how':'scope','fact':'third_party_payout_allowed','scope':'lendco/servicing','moved_to':'lendco/collections'}]),
               (extra('x13',scope='lendco/collections',evidence=[row('third_party_payout_allowed','FALSE'),row('maker_may_reconcile','FALSE',final=True)]),             # nor is an ordinary no
                [{'kind':'REFUSAL_DROPPED','how':'scope','fact':'third_party_payout_allowed','scope':'lendco/servicing','moved_to':'lendco/collections'}]),
               (extra('x14',methods=[ask('ask-owner-third-party@1','third_party_payout_allowed')],grants=['action:ask-owner-third-party@1']),   # J2 Pro: "A rule cannot say it more loosely"
                [{'kind':'REFUSAL_DROPPED','how':'looser','method':'ask-owner-third-party@1','fact':'third_party_payout_allowed'}]),
               (extra('x15',rules=[r('R-THIRD@1','third_party_payout_allowed',[['refund_due']])]),[{'kind':'REFUSAL_DROPPED','how':'looser','rule':'R-THIRD@1','fact':'third_party_payout_allowed'}]),
               (extra('x16',evidence=[row('owner_approved_refund','TRUE')]),[{'kind':'ASK_DROPPED','how':'answer','fact':'owner_approved_refund','source':'fixture/test','reads':'TRUE'}]),
               (extra('x17',evidence=[row('owner_approved_refund','TRUE',final=True)]),[{'kind':'ASK_DROPPED','how':'answer','fact':'owner_approved_refund','source':'fixture/test','reads':'TRUE'}]),
               (extra('x18',evidence=[row('owner_approved_refund','TRUE',depends_on=[{'predicate':'quarter_closed','version':'q4'}])]),   # a yes that rests on a row still to come
                [{'kind':'ASK_DROPPED','how':'answer','fact':'owner_approved_refund','source':'fixture/test','reads':'UNKNOWN'}]),
               (extra('x19',methods=[m('assume-approval@1','owner_approved_refund')],grants=['action:assume-approval@1']),[{'kind':'ASK_DROPPED','how':'method','method':'assume-approval@1','fact':'owner_approved_refund'}]),
               (extra('x20',methods=[ask('ask-team-lead@1','owner_approved_refund','team-lead')],grants=['action:ask-team-lead@1']),[{'kind':'ASK_DROPPED','how':'method','method':'ask-team-lead@1','fact':'owner_approved_refund'}]),   # another question is another way to the answer
               (extra('x21',rules=[r('R-APPROVED@1','owner_approved_refund',[['refund_due']])]),[{'kind':'ASK_DROPPED','how':'rule','rule':'R-APPROVED@1','fact':'owner_approved_refund'}]),
               (extra('x22',budget={'money':50}),[{'kind':'CEILING_RAISED','how':'budget','dimension':'money','was':10,'now':50}]),
               (extra('x23',providers={'owner-channel':5}),[{'kind':'CEILING_RAISED','how':'provider','provider':'owner-channel','was':1,'now':5}]),
               (extra('x24',rules=[r('R-APPROVED@1','owner_approved_refund',[['refund_due']])],methods=[m('pay-fast@1','refund_paid')]),   # findings come in the order of the kinds, whatever order the pack is read in
                [way('pay-fast@1','pay-to-third-party@1',dropped=['third_party_payout_allowed'],grant='action:pay-fast@1',cheaper=['money']),{'kind':'ASK_DROPPED','how':'rule','rule':'R-APPROVED@1','fact':'owner_approved_refund'}]),
               (pack('115_servicing_loosens'),[rule(dropped=['source_record_named']),{'kind':'REFUSAL_DROPPED','how':'decision','fact':'third_party_payout_allowed','scope':'lendco/servicing','source':'team:lendco/servicing'},
                                               {'kind':'ASK_DROPPED','how':'answer','fact':'owner_approved_refund','source':'team:lendco/servicing','reads':'TRUE'}]))
        other=((stopped,extra('y1',grants=['action:pay-to-third-party@1']),[{'kind':'REFUSAL_DROPPED','how':'grant','grant':'action:pay-to-third-party@1'}]),
               (receipt,extra('y2',rules=[r('R-RECEIPT@1','receipt_filed',[['refund_paid']])]),[{'kind':'CONDITION_DROPPED','how':'derived','rule':'R-RECEIPT@1','head':'receipt_filed'}]),
               ([pack(n) for n in DESK],pack('119_platform_allows_itself'),[{'kind':'REFUSAL_DROPPED','how':'looser','method':'permit-root@1','fact':'may:privilege_escalation'},
                                                                            {'kind':'CEILING_RAISED','how':'budget','dimension':'compute','was':10,'now':50},{'kind':'CEILING_RAISED','how':'budget','dimension':'money','was':10,'now':50}]))
        before=json.dumps(self.parents);seen=set()
        for parents,child,want in [(self.parents,c,w) for c,w in cases]+list(other):
            State.from_packs(parents+[child])   # the kernel itself applies every one of these packs: that is the gap the check stands in
            found=relaxations(parents,child);self.assertEqual(said(found),want,child['id']);seen|={(f['kind'],f['how']) for f in found}
            for f in found:   # every finding carries one sentence that names what it is about
                self.assertTrue(type(f['line']) is str and all(str(f[k]) in f['line'] for k in ('rule','method','fact','grant','dimension','provider','beside','moved_to','was','now') if f.get(k) is not None),f)
                self.assertTrue(all(x in f['line'] for k in ('dropped','cheaper','methods') for x in f.get(k,[])),f)
        self.assertEqual((seen,json.dumps(self.parents),KINDS),(self.WAYS,before,('CONDITION_DROPPED','REFUSAL_DROPPED','ASK_DROPPED','CEILING_RAISED')))   # all thirteen ways; the check reads and changes nothing it is handed
        self.assertEqual(relaxations(self.parents,next(c for c,_ in cases if c['id']=='x18'))[0]['line'],'the pack carries a TRUE row on owner_approved_refund, which the parent asks about: it answers for the party that was to be asked (it reads once what it rests on arrives)')
        # What is not the child's doing is not named.
        kinds=lambda child,parents:[(f['kind'],f['how']) for f in relaxations(parents,child)]
        self.assertEqual(kinds(extra('z1',grants=['action:pay-to-third-party@1'],revoke_grants=['action:pay-to-third-party@1']),stopped),[])   # granted and revoked in one pack: the kernel revokes
        self.assertEqual(kinds(extra('z2'),stopped+[extra('granted-again',grants=['action:pay-to-third-party@1'])]),[])   # what the parents themselves gave back
        self.assertEqual(kinds(extra('z3'),self.parents+[extra('answered',evidence=[row('owner_approved_refund','TRUE')])]),[])   # an answer the parents already carry
        self.assertEqual(kinds(extra('z4',evidence=[row('owner_approved_refund','TRUE',version='t2')]),self.parents+[extra('answered',evidence=[row('owner_approved_refund','TRUE')])]),[])   # the same answer again, by the child
        ruled=self.parents+[extra('ruled',rules=[r('R-CHECKED@1','payee_account_checked',[['refund_due']])])]
        self.assertEqual(kinds(extra('z5',methods=[m('assume-checked@1','payee_account_checked')]),ruled),[])   # a step for a fact a rule already stands on: the kernel never consults it
        unapproved=self.parents+[extra('idle',methods=[dict(m('pay-idle@1','refund_paid'),approved=False)])]
        self.assertEqual(said(relaxations(unapproved,extra('z6',methods=[m('pay-fast@1','refund_paid')])))[0]['beside'],'pay-to-third-party@1')   # a step of the parent that is not approved is no way to keep whole
        # A parent rule with two alternatives: the finding is named against the one the child's alternative came from; and a new way against the way of the parent it keeps most of.
        notify=[pack(n) for n in ('00_goal','01_domain','02_methods','03_approval','04_admission','06_notify')]
        found=relaxations(notify,extra('x25',rules=[r('R-ORDER@3','order_complete',[['original_delivered'],['replacement_delivered']],'R-ORDER@2')]))
        self.assertEqual([(f['kind'],f['how'],f['alternative'],f['dropped']) for f in found],[('CONDITION_DROPPED','rule',2,['customer_notified'])])
        two=self.parents+[extra('two-ways',methods=[m('file-short@1','receipt_filed',['refund_paid'],grant='action:file@1'),m('file-full@1','receipt_filed',['refund_paid','payment_reconciled','source_record_named'],grant='action:file@1')])]
        found=relaxations(two,extra('x26',methods=[m('file-early@1','receipt_filed',['payment_reconciled','source_record_named'],grant='action:file@1')]))
        self.assertEqual(said(found),[{'kind':'CONDITION_DROPPED','how':'method','method':'file-early@1','effect':'receipt_filed','beside':'file-full@1','dropped':['refund_paid'],'grant':None,'provider':None,'cheaper':[]}])
        # A step of the parent that does not say it is approved is a way to keep whole, and a dimension its cost leaves out costs nothing there.
        lean=self.parents+[extra('lean',methods=[bare(m('file-lean@1','receipt_filed',['refund_paid'],grant='action:file@1',cost={'compute':1}))])]
        self.assertEqual(relaxations(lean,extra('n16',methods=[m('file-also@1','receipt_filed',['refund_paid'],grant='action:file@1',cost={'compute':1,'money':0,'attention':0})])),[])
        self.assertEqual(said(relaxations(lean,extra('x27',methods=[m('file-early@1','receipt_filed',[],grant='action:file@1',cost={'compute':1})]))),
                         [{'kind':'CONDITION_DROPPED','how':'method','method':'file-early@1','effect':'receipt_filed','beside':'file-lean@1','dropped':['refund_paid'],'grant':None,'provider':None,'cheaper':[]}])
        asks=pack('113_servicing_standing_rules');quiet=[self.parents[0],dict(asks,methods=[bare(asks['methods'][0])])]   # and so is a question that does not say it is approved
        self.assertEqual(said(relaxations(quiet,extra('x28',evidence=[row('owner_approved_refund','TRUE')]))),[{'kind':'ASK_DROPPED','how':'answer','fact':'owner_approved_refund','source':'fixture/test','reads':'TRUE'}])
    def test_what_the_check_does_not_read(self):
        # Known limits, pinned: each child below relaxes something in effect, the kernel applies it, and the check names nothing.
        told=extra('l1',evidence=[row('payee_account_checked','TRUE')])   # an ordinary row that says a condition is true: the always step is skipped
        self.assertEqual((relaxations(self.parents,told),'check-payee-account@1' in look(world(PRACTICE,told))['actions'],'check-payee-account@1' in look(world(PRACTICE))['actions']),([],False,True))
        aims=extra('l2',goals=[],preference=['money','compute','attention'])   # the standing goal dropped, the preference turned
        self.assertEqual((relaxations(self.parents,aims),Kernel(world(PRACTICE,aims)).run_standing(execute=True)['status']),([],'NO_STANDING_GOAL'))
        first=extra('l3',grants=['action:check-payee-account@1'])   # a grant the parent merely never gave is no refusal
        self.assertEqual(relaxations(self.parents[0],first),[])
        review=pack('116_pack_review');fact=review['rules'][0]['branches'][0][0]
        declared=extra('l4',methods=[m('declare-narrow@1',fact)],grants=['action:declare-narrow@1'],providers={'local-provider':1})   # a step of the child's own for a condition the parent leaves to evidence
        x=look(State.from_packs([review,declared]));self.assertEqual((relaxations([review],declared),x['status'],x['actions']),([],'LOCAL_MODEL_EFFECTS_RECORDED',['declare-narrow@1']))
        self.assertEqual([(f['kind'],f['how']) for f in relaxations([review],extra('l5',rules=[r('R-SAYS@1',fact,[['anything']])]))],[('CONDITION_DROPPED','derived')])   # the same by a rule is named
    def test_packs_the_kernel_refuses_are_refused_by_the_check(self):
        for bad in (extra('b1',rules=[r('R-OTHER@1','refund_settled',[['refund_paid']])]),   # a rule on a standing head that does not cite what it replaces
                    extra('b2',methods=[m('pay-to-borrower@1','refund_paid')]),              # a method id twice
                    extra('b3',budget={'money':-1}),{'id':'b4'},'not a pack',None):
            for check in (relaxations,verdict,install_rule):
                with self.assertRaises(ValueError,msg=repr(bad)):check(self.parents,bad)
        with self.assertRaises(ValueError):relaxations([extra('p',budget={'money':-1})],extra('c'))
        for bad in (None,'112_servicing_team',(self.parents[0],),7):
            for check in (relaxations,verdict,install_rule):
                with self.assertRaises(ValueError,msg=repr(bad)):check(bad,extra('c'))
    def test_the_kernel_applies_a_loosening_pack_and_the_review_of_exactly_that_pack_blocks_its_install(self):
        loosens,pick=pack('115_servicing_loosens'),pack('114_practice_money_movement')
        s=world(LOOSE);x=look(s)   # the kernel has no such check: the pack applies, and the look pays a third party, unasked, without naming the source record
        self.assertEqual((x['status'],x['actions'],open_asks(s),s.fact('source_record_named')['truth']),('LOCAL_MODEL_EFFECTS_RECORDED',['pay-to-third-party@1','reconcile-by-checker@1'],{},'UNKNOWN'))
        # The review is one decision, named by the child and the digest of exactly the packs compared; the install rule rests on that name.
        v,found=verdict(self.parents,loosens),relaxations(self.parents,loosens);name='115_servicing_loosens@pair-'+digest([self.parents,loosens])[:12]
        self.assertEqual(v,{'predicate':'narrows:'+name,'truth':'FALSE','verified':True,'final':True,'source':'adapter:refusals/narrowing@1','version':'pair-'+digest([self.parents,loosens])[:12],
                            'child':'115_servicing_loosens','parents':PRACTICE,'relaxed':found})
        self.assertEqual(install_rule(self.parents,loosens),{'id':'R-INSTALL:'+name,'head':'installable:'+name,'branches':[['narrows:'+name]],'approved':True,'source':'reviewed/child-narrows-never-relaxes'})
        yes=verdict(self.parents[:2],pick);self.assertEqual((yes['truth'],yes['final'],yes['relaxed'],yes['predicate']),('TRUE',True,[],'narrows:114_practice_money_movement@pair-'+digest([self.parents[:2],pick])[:12]))
        self.assertEqual((verdict(self.parents[0],self.parents[1])['parents'],verdict(self.parents[0],self.parents[1])['predicate']),(['112_servicing_team'],'narrows:113_servicing_standing_rules@pair-'+digest([[self.parents[0]],self.parents[1]])[:12]))
        desk116=pack('116_pack_review');rules=[install_rule(self.parents,loosens),install_rule(self.parents[:2],pick)]
        self.assertEqual((desk116['rules'],desk116['goals'],pack('117_review_of_loosening')['evidence'],pack('118_review_of_practice')['evidence']),(rules,[x['head'] for x in rules],[v],[yes]))
        # Case 53: both reviews are loaded. The install of the loosening pack is refused on its own review; the pick's is supported by its own; neither stands in for the other.
        s=world(REVIEW);k=Kernel(s);runs=k.run_standing(execute=True)['runs']
        self.assertEqual([(x['goal'],x['status'],x['actions'],x['model_receipts']) for x in runs],[(rules[0]['head'],'REFUSED',[],[]),(rules[1]['head'],'SUPPORTED_BY_EVIDENCE',[],[])])
        self.assertEqual((runs[0]['stop_reasons'],ops(runs[0])[1:3],s.budget),(['REFUSED'],[('REFINE',rules[0]['head']),('REFUSED',v['predicate'])],{'compute':10,'money':10,'attention':3}))
        self.assertEqual((k.on_event(row(v['predicate'],'TRUE'))['status'],[x['status'] for x in k.run_standing(execute=True)['runs']]),('DECISION_STANDS',['REFUSED','SUPPORTED_BY_EVIDENCE']))   # an ordinary row that says otherwise is turned away
        # Without its own review a pack is not installable: evidence is wanted. The review of another child, loaded or arriving later, changes nothing for it.
        s=world(['116_pack_review','118_review_of_practice']);self.assertEqual([x['status'] for x in Kernel(s).run_standing(execute=True)['runs']],['QUERY_EVIDENCE','SUPPORTED_BY_EVIDENCE'])
        s=world(['116_pack_review','117_review_of_loosening']);k=Kernel(s);self.assertEqual([x['status'] for x in k.run_standing(execute=True)['runs']],['REFUSED','QUERY_EVIDENCE'])
        late=k.on_event(yes,execute=True);self.assertEqual((late['affected'],[x['status'] for x in late['runs']],[x['status'] for x in k.run_standing(execute=True)['runs']]),([rules[1]['head']],['SUPPORTED_BY_EVIDENCE'],['REFUSED','SUPPORTED_BY_EVIDENCE']))
        # Nor does the review of an older text. The pick is edited after its review so that it lifts the owner's never: its name changes with its text,
        # the old yes no longer answers, and the new review says no.
        edited=dict(pick,evidence=pick['evidence']+[row('third_party_payout_allowed','TRUE',final=True)]);now=install_rule(self.parents[:2],edited)
        self.assertNotEqual(now['head'],rules[1]['head']);self.assertEqual((verdict(self.parents[:2],edited)['truth'],[f['kind'] for f in verdict(self.parents[:2],edited)['relaxed']]),('FALSE',['REFUSAL_DROPPED']))
        board=extra('board',scope='lendco/pack-review',goals=[now['head']],rules=[now])
        self.assertEqual((look(State.from_packs([board,pack('118_review_of_practice')]))['status'],look(State.from_packs([board,extra('fresh',evidence=[verdict(self.parents[:2],edited)])]))['status']),('QUERY_EVIDENCE','REFUSED'))
        self.assertNotEqual(install_rule(self.parents[:1],pick)['head'],rules[1]['head'])   # other parents, another name
        # Known limit, pinned. A review is believed by its name: in the review's own State another decision under that name replaces it, whoever sent it.
        s=world(REVIEW,extra('forged',evidence=[dict(v,truth='TRUE',relaxed=[],source='anyone')]));self.assertEqual(look(s)['status'],'SUPPORTED_BY_EVIDENCE')


class RecordTests(unittest.TestCase):
    PACKS={'110_ops_desk':'2b32ac4d02434a7f',
           '111_requested_actions':'fd8fe5646b6a8c8d',
           '112_servicing_team':'fba00af75e410c0a',
           '113_servicing_standing_rules':'cfd040d0b02363c3',
           '114_practice_money_movement':'455c53e61de9d393',
           '115_servicing_loosens':'a75d376e79b11499',
           '116_pack_review':'ebd808c55ef6a975',
           '117_review_of_loosening':'58c84037fe43996e',
           '118_review_of_practice':'211d9e2158d00dc2',
           '119_platform_allows_itself':'52625e4817a73dfe'}
    def test_the_ten_packs_are_these(self):
        # A pin, not a model: the cases and the sequence rest on these ten packs, so a changed word in any of them (a line, a source, a version, a cost) fails here.
        # What the words must be is asserted in plain text above; this catches the rest.
        self.assertEqual({n:digest(pack(n))[:16] for n in self.PACKS},self.PACKS)
    def test_the_recorded_sequence_is_what_the_lab_does_again(self):
        data=json.loads((ROOT/'results'/'actual_run_records.json').read_text())
        self.assertEqual(json.dumps(scenes()['refusals'],sort_keys=True),json.dumps(data['scenes']['refusals'],sort_keys=True))
        self.assertEqual({c['id']:(c['packs'],[x['status'] for x in c['run']['runs']]) for c in data['cases'] if c['id'][:2] in ('51','52','53')},
                         {'51_refused_class':(DESK,RefusedClassTests.WANT),'52_standing_rules':(TEAM,['WAITING']),'53_child_relaxes':(REVIEW,['REFUSED','SUPPORTED_BY_EVIDENCE'])})
    def test_the_independent_checks_pass_on_the_record_and_fail_on_forged_ones(self):
        spec=importlib.util.spec_from_file_location('independent_verify_for_refusals',ROOT/'qa'/'independent_verify.py')
        v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);ns={}
        exec(compile((ROOT/'qa'/'checks'/'refusals.py').read_text(),'refusals_checks','exec'),ns)   # as the verifier loads it
        data=json.loads((ROOT/'results'/'actual_run_records.json').read_text())
        got={cid:ok for cid,ok,_ in ns['checks'](data,ROOT,v.sha,v.check_chain)};self.assertEqual(([c[:3] for c in got],all(got.values())),(['S6%d'%i for i in range(10)],True))
        files={n:json.loads((ROOT/'scenarios'/(n+'.json')).read_text()) for n in ns['NAMES']};run=lambda d,p=files:ns['claims'](d,p,v.sha)   # the nine claims of S60 to S68, on a forged copy of the record or of the packs
        self.assertEqual([t for t in v.inspect(data)['checks'] if t['id'].startswith(('S6','refusals')) and not t['pass']],[])   # and the verifier runs the module (it reads only the record)
        case=lambda d,cid:[c for c in d['cases'] if c['id']==cid][0];seq=lambda d:d['scenes']['refusals']
        for change,expect in ((lambda d:seq(d)['desk']['rescreened'].update(affected=['due_list_exported']),'S60'),
                              (lambda d:case(d,'51_refused_class')['run']['runs'][3].update(status='LOCAL_MODEL_EFFECTS_RECORDED'),'S61'),
                              (lambda d:case(d,'51_refused_class')['run']['runs'][1]['provenance'].pop(),'S61'),
                              (lambda d:case(d,'51_refused_class')['derived_state']['facts']['lendco/operations|may:privilege_escalation'].update(truth='TRUE'),'S61'),
                              (lambda d:seq(d)['desk']['allow_later'].update(status='RECONCILED'),'S62'),
                              (lambda d:seq(d)['desk']['after']['providers'].update({'local-provider':0}),'S62'),
                              (lambda d:case(d,'52_standing_rules')['outcome'].update(pending=['reconcile-by-maker@1']),'S63'),
                              (lambda d:case(d,'52_standing_rules')['derived_state']['facts']['lendco/servicing|third_party_payout_allowed'].update(truth='TRUE'),'S63'),
                              (lambda d:seq(d)['no']['answered_no']['runs'][0].update(status='WAITING'),'S64'),
                              (lambda d:seq(d)['yes']['after_look']['open_asks']['lendco/servicing|owner_approved_refund']['issued']['ask'].update(to='team-lead'),'S64'),
                              (lambda d:seq(d)['no'].update(packs=['112_servicing_team']),'S64'),
                              (lambda d:[e for e in seq(d)['no']['answered_no']['runs'][0]['trace'] if e['operation']=='ASK_CLOSED'][0]['data'].update(truth='TRUE'),'S64'),
                              (lambda d:case(d,'51_refused_class')['run']['runs'][5]['proof'].pop(),'S61'),
                              (lambda d:case(d,'51_refused_class')['run']['runs'][2]['learning_record'].update(learning_sha256='0'*64),'S61'),
                              (lambda d:seq(d)['narrowing']['practice']['relaxed'].append({'kind':'CEILING_RAISED'}),'S65'),
                              (lambda d:seq(d)['narrowing']['loosened']['relaxed'].pop(),'S66'),
                              (lambda d:seq(d)['desk']['later_pack']['relaxed'][0].update(line='nothing was relaxed'),'S66'),
                              (lambda d:seq(d)['narrowing']['loosened']['look']['runs'][0].update(actions=['pay-to-borrower@1','reconcile-by-checker@1']),'S67'),
                              (lambda d:case(d,'53_child_relaxes')['derived_state']['budget_after'].update(money=0),'S68'),
                              (lambda d:case(d,'53_child_relaxes')['outcome'].update(status='METHOD_ABSENT'),'S68')):
            d=json.loads(json.dumps(data));change(d);self.assertIn(expect,[cid[:3] for cid,ok in run(d).items() if not ok])
        for change,expect in ((lambda p:p['110_ops_desk']['evidence'].pop(1),'S60'),                                                   # a desk that leaves a class unruled
                              (lambda p:p['110_ops_desk']['providers'].update({'local-provider':0}),'S61'),                            # no slot for the steps that ran
                              (lambda p:p['111_requested_actions']['methods'][0]['requires'].__setitem__(0,'screened:restart-ledger-sync@1'),'S60'),   # a step that requires the bare name
                              (lambda p:p['118_review_of_practice']['evidence'][0].update(predicate=p['117_review_of_loosening']['evidence'][0]['predicate']),'S68')):   # the pick's review under the other pack's name
            p=json.loads(json.dumps(files));change(p);self.assertIn(expect,[cid[:3] for cid,ok in run(data,p).items() if not ok])


# ---- Added in the confirming review round (2026-11-14). Additions only: nothing above this line was changed, and nothing below changes what
# the delivery does. Each test pins what the delivery does today. Three kinds: a limit the README states (where it names a test, the test is
# here); a request or a child pack at an edge, where a changed extension would read otherwise (each such line stands for a change to
# extensions/refusals_classes.py or extensions/refusals_narrowing.py that the tests above let pass); and the words of the two extensions,
# word for word. What was left standing after two sweeps of such changes changes nothing the extensions do on any pack this lab can load.
def refusal_of(call,*args):   # the words a refusal is made in
    try:call(*args)
    except ValueError as e:return str(e)


class ClassifierEdgeTests(unittest.TestCase):
    # The ten classes as the table words them. The words are pinned as they stand: the text of unreadable_command names six kinds of
    # character and is narrower than the test itself (any character outside the plain ones), which the README states among the limits.
    TEXTS={'history_rewrite':'rewrites or discards shared git history (git push --force, git clean -f)',
           'recursive_delete':'deletes a tree outside the build folders (rm -r)',
           'disk_or_system':'touches disks, mounts or system services (dd, mkfs, mount, launchctl, chmod -R)',
           'remote_mutation':'changes a remote or shared system (ssh, rsync, kubectl, psql, a publish)',
           'privilege_escalation':'runs as another user (sudo, su, doas, pkexec)',
           'unreadable_command':'is not made of plain words (a quote, a substitution, a combinator, a redirection, a glob, a control character)',
           'destructive_tool':'a tool named with a delete-class verb (delete, drop, purge, trash)',
           'bulk_tool':'a tool that changes many records at once (bulk, mass, batch modify)',
           'credential_path':'a path inside a credential store (.ssh, .aws, .gnupg, a keychain)',
           'private_host':'anything but a plain http(s) URL to a public address or name (loopback, private, link-local, multicast and reserved ranges, a local name, another scheme)'}
    def test_requests_at_the_edges_of_the_table(self):
        for text in ('http://metadata/','http://kubernetes/api','http://redis:6379/'):self.assertEqual(classes_of(host(text)),['private_host'],text)   # one word alone is no public name
        for text in ('crm_v2_delete','mcp:drive:delete'):self.assertEqual(classes_of(tool(text)),['destructive_tool'],text)   # a tool's name may carry a digit and a colon
        self.assertEqual((classes_of(tool('labels')),classes_of(tool('apply')),classes_of(tool('gmail_apply_labels'))),([],[],['bulk_tool']))   # applying labels is both words, alone or among others
        for text in ('make clean -f Makefile',   # history is rewritten by git, not by any program that cleans or pushes
                     'git clean -x',             # the letter of the flag is f
                     'rm report.txt',            # a flag begins with a dash: a file name with an r in it is none
                     'rm -x notes.txt',          # the letters of the recursive flag are r and R
                     'chmod -x run.sh',          # and of chmod and chown, R
                     'rm -rf build ',            # a space at the end is no word, so no path beside the build folder
                     'mkfifo pipe',              # mkfs and what begins with it, not what begins like it
                     'x:sudo ls','x@sudo ls','x,sudo ls','x%sudo ls','x~sudo ls',   # these five characters are part of a word: they do not set sudo apart as a word of its own
                     'xsudo ls','sudo= ls'):     # only a leading = is taken off a word
            self.assertEqual(classes_of(cmd(text)),[],text)
        self.assertEqual(classes_of(cmd('x+sudo ls')),['unreadable_command'])   # a plus sign is part of a word too, and makes the command one that is not plain
        self.assertEqual(classes_of(path('/home/a/.sshx/id')),[])   # dots and spaces are dropped at the end of a part, nothing else
        for text in ('/home/a/.ßh/id',                        # letters are folded as casefold folds them: a sharp s is ss
                     '/home/a/.ｓｓｈ/id',             # and full-width letters are read as the plain ones
                     '/home/a/.ssh /id'):                     # any white space at the ends of a part is dropped, not only the space
            self.assertEqual(classes_of(path(text)),['credential_path'],repr(text))
        class Kind(str):pass
        for bad in (path('reports/a\tb.csv'),tool('drop=table'),{'kind':Kind('command'),'text':'ls'}):   # a tab in a path, a tool named with another sign, a kind that is not plain text
            with self.assertRaises(ValueError,msg=repr(bad)):classes_of(bad)
    def test_the_plain_test_refuses_everyday_commands(self):
        # Known limit, pinned. A command with any character outside letters, digits, space and _ . / = : @ , % ~ - is in unreadable_command:
        # a plus sign too, which is none of the six kinds the class's text names. At the recorded desk such a step is refused.
        for text in ('chmod +x run.sh','date +%F'):
            self.assertEqual(classes_of(cmd(text)),['unreadable_command'],text)
            x=look(desk(asked_for('step@1','step_done',cmd(text))));self.assertEqual((x['status'],x['stop_reasons'],x['actions']),('REFUSED',['REFUSED'],[]),text)
        self.assertEqual((classes_of(cmd('chmod 755 run.sh')),C.PLAIN.pattern),([],r'[A-Za-z0-9 _./=:@,%~-]+'))
    def test_the_words_of_the_table_and_of_a_refusal(self):
        self.assertEqual({c:what for c,(_,what,_) in CLASSES.items()},self.TEXTS)
        shape='A request is {kind: command, tool, path or host; text: what is asked}, at most 2000 characters'
        self.assertEqual([refusal_of(classes_of,bad) for bad in (None,tool('delete draft'),host('http://a b/'),path('~/.s?h/id'))],
                         [shape,'A tool is named by letters, digits and _ . : / -','A host or an address is printable text without spaces','A path names one place: no control character, no wildcard, no variable'])
        self.assertEqual((refusal_of(screened,'',cmd('ls')),refusal_of(prerequisites,None,cmd('ls')),refusal_of(unscreened,None),refusal_of(unruled,None)),
                         ('A step is named','A step is named','A pack holds its methods and its evidence in lists','The packs are one pack or a list of packs, in load order'))
        bad=[extra('b',budget={'money':-1})];self.assertEqual(refusal_of(unruled,bad),'The kernel refuses these packs: '+refusal_of(State.from_packs,bad))   # the kernel's own words, after the audit's
    def test_the_audit_of_a_queue_at_its_edges(self):
        queue=pack('111_requested_actions');own=named('restart-ledger-sync@1',queue['methods'][0]['request'])
        def forged(change):
            q=json.loads(json.dumps(queue));change(q);return unscreened(q)
        self.assertEqual((unscreened({}),unscreened(pack('110_ops_desk'),every=True)),([],[]))   # a pack without steps has none to name
        self.assertEqual(unscreened({'methods':[{'id':'x@1'}]},every=True),['x@1: it carries no request, so nothing was screened'])   # a step that names no action kind is no question to a person
        self.assertEqual(forged(lambda q:q['methods'][0]['requires'].append(7)),[])   # a prerequisite that is no text is no screening, and the audit does not stop on it
        self.assertEqual(forged(lambda q:q['methods'][0]['requires'].append('screened_twice')),[])   # a screening is named screened:<step>@<request>: a fact that merely begins like it is none
        self.assertEqual(forged(lambda q:q['methods'][5]['requires'].extend([own,'screened:x'])),['export-due-list@1: it requires the screening of another request (%s, screened:x)'%own])
        self.assertEqual(forged(lambda q:q['methods'][0].update(request={'kind':'shell','text':'ls'})),
                         ['restart-ledger-sync@1: its request cannot be read (A request is {kind: command, tool, path or host; text: what is asked}, at most 2000 characters)'])


class RefusedLookLimitTests(unittest.TestCase):
    def test_a_question_that_cannot_be_planned_counts_as_a_ruling_and_hides_the_refusal_after_it(self):
        # Known limit, pinned. The audit takes an approved question on a class as a ruling and does not ask whether the question itself can be
        # planned. A question with a prerequisite of its own that is unknown yields no plan: read before a refused class it names the look
        # (evidence is wanted) and the refusal after it is not read, at a desk the audit passes. Nothing runs, nobody is asked, nothing is paid.
        two=cmd('sudo rsync -a loans/ backup:/srv/loans/');name=named('step@1',two);p=pack('110_ops_desk')
        def asking(requires):
            return [dict(p,id='desk-asks',evidence=[e for e in p['evidence'] if e['predicate']!='may:remote_mutation']),
                    extra('ask-remote',methods=[dict(ask('ask-owner-remote@1','may:remote_mutation'),requires=requires)],grants=['action:ask-owner-remote@1'],providers={'owner-channel':1})]
        self.assertEqual((classes_of(two),unruled(asking(['ticket_open'])),unruled(asking([]))),(['remote_mutation','privilege_escalation'],[],[]))   # ruled, says the audit, either way
        s=State.from_packs(asking(['ticket_open'])+[asked_for('step@1','step_done',two)]);before=books(s);x=look(s)
        self.assertEqual((x['status'],x['stop_reasons'],x['actions'],x['model_receipts'],open_asks(s),books(s)),('QUERY_EVIDENCE',['QUERY_EVIDENCE'],[],[],{},before))
        self.assertEqual(ops(x)[1:-2],[('METHOD_MATCH','step_done'),('RETAIN',name),('METHOD_MATCH','may:remote_mutation'),('QUERY_EVIDENCE','ticket_open')])   # the decision on may:privilege_escalation is never read
        k=Kernel(s);k.on_event(row('ticket_open','TRUE'));x=look(s)   # the evidence it asked for: the question can be planned, the refusal is read, and no question is put for a step that is refused anyway
        self.assertEqual((x['status'],x['stop_reasons'],x['actions'],x['model_receipts'],open_asks(s),s.budget),('REFUSED',['REFUSED'],[],[],{},{'compute':10,'money':10,'attention':3}))
        s=State.from_packs(asking([])+[asked_for('step@1','step_done',two)]);x=look(s)   # a question that needs nothing of its own: refused at once
        self.assertEqual((x['status'],x['stop_reasons'],open_asks(s)),('REFUSED',['REFUSED'],{}))
    def test_a_refusal_names_the_run_unless_an_evidence_conflict_is_among_the_reasons(self):
        # Where a refused route is one of several reasons, the kernel names the run by its ranking. One goal, two alternatives: `b` is refused
        # by decision and `a` fails for another reason. Beside each of the six reasons ranked below a refusal the run is named REFUSED and the
        # other reason is in stop_reasons. Known limit, pinned: an evidence conflict ranks above, so beside one the run is named
        # EVIDENCE_CONFLICT and the refusal is the reason left in stop_reasons. Nothing runs in any of them.
        def world(*rows,**more):
            return State.from_packs([extra('w',scope='lendco/x',goals=['g'],rules=[r('R@1','g',[['a'],['b']])],evidence=[row('b','FALSE',final=True)]+list(rows),**more)])
        held=dict(grants=['action:make-a@1'],providers={'local-provider':1})
        beside={'QUERY_EVIDENCE':world(),                                                                   # nothing is known of a, and nothing makes it
                'METHOD_ABSENT':world(row('a','FALSE')),                                                    # a is false, and nothing makes it
                'AUTHORITY_REQUIRED':world(methods=[m('make-a@1','a')],providers={'local-provider':1}),     # a step for a whose grant is not held
                'PROVIDER_REQUIRED':world(methods=[m('make-a@1','a')],grants=['action:make-a@1']),          # whose provider has no slot
                'RESOURCE_REQUIRED':world(methods=[m('make-a@1','a',cost={'compute':1,'money':11,'attention':0})],**held),   # that costs more than the budget
                'CYCLE_LIMIT':world(methods=[m('make-a@1','a',['g'])],**held)}                              # that requires the goal itself
        for reason,s in beside.items():
            before=books(s);x=look(s)
            self.assertEqual((x['status'],x['stop_reasons'],x['actions'],x['model_receipts'],books(s)),('REFUSED',sorted([reason,'REFUSED']),[],[],before),reason)
        s=world(row('g','FALSE'),row('a','TRUE'));before=books(s);x=look(s)   # a holds by evidence while the goal reads false: a conflict
        self.assertEqual((x['status'],x['stop_reasons'],x['actions'],x['model_receipts'],books(s)),('EVIDENCE_CONFLICT',['EVIDENCE_CONFLICT','REFUSED'],[],[],before))
        # The same at the recorded desk: a goal with two alternatives, one closed by evidence under an ordinary no on the goal, the other the refused step.
        either=extra('either',goals=['either'],rules=[r('R-EITHER@1','either',[['x'],['step_done']])],evidence=[row('x','TRUE'),row('either','FALSE')])
        s=desk(asked_for('step@1','step_done',cmd('sudo rsync -a loans/ backup:/srv/loans/')),either);before=books(s);x=look(s)
        self.assertEqual((x['goal'],x['status'],x['stop_reasons'],x['actions'],books(s)),('either','EVIDENCE_CONFLICT',['EVIDENCE_CONFLICT','REFUSED'],[],before))


class NarrowingEdgeTests(unittest.TestCase):
    def setUp(self):self.parents=[pack(n) for n in PRACTICE]
    def test_children_at_the_edges_of_the_check(self):
        # A yes by decision among the parents is no refusal: a child that only narrows is not named for it, and a child that moves the scope is named for the two refusals only.
        held=self.parents+[extra('held',evidence=[row('weekend_payout_allowed','TRUE',final=True)])]
        self.assertEqual(relaxations(held,extra('e1',methods=[m('file-receipt@1','receipt_filed',['refund_paid'])],grants=['action:file-receipt@1'])),[])
        self.assertEqual([(f['how'],f['fact']) for f in relaxations(held,extra('x29',scope='lendco/collections'))],[('scope','maker_may_reconcile'),('scope','third_party_payout_allowed')])
        # A question of the parent that is not approved asks nobody: a yes on its fact answers for no one.
        asks=pack('113_servicing_standing_rules');idle=[self.parents[0],dict(asks,methods=[dict(asks['methods'][0],approved=False)])]
        self.assertEqual(relaxations(idle,extra('e2',evidence=[row('owner_approved_refund','TRUE')])),[])
        # A yes of the parents' own on the asked fact that does not read yet is not the child's doing.
        waiting=self.parents+[extra('pending-yes',evidence=[row('owner_approved_refund','TRUE',depends_on=[{'predicate':'quarter_closed','version':'q4'}])])]
        self.assertEqual(relaxations(waiting,extra('e3')),[])
        # A refusal that an earlier parent already left behind (the parents themselves span two scopes) is named for the pack that left it, not again for a later one.
        for first in ('lendco/a','lendco/z'):   # whichever way the names of the scopes sort
            left=[extra('first',scope=first,evidence=[row('x_allowed','FALSE',final=True)]),extra('second',scope='lendco/b')]
            self.assertEqual(([(f['how'],f['fact'],f['scope'],f['moved_to']) for f in relaxations(left[:1],left[1])],relaxations(left,extra('e4',scope='lendco/c'))),([('scope','x_allowed',first,'lendco/b')],[]),first)
        # Only a yes answers a question: a child that says the asked fact is unknown is not named, and a yes is named over a no of the parents' that is no decision.
        self.assertEqual(relaxations(self.parents,extra('e5',evidence=[row('owner_approved_refund','UNKNOWN')])),[])
        denied=self.parents+[extra('not-yet',evidence=[row('owner_approved_refund','FALSE')])]
        self.assertEqual([(f['how'],f['fact'],f['reads']) for f in relaxations(denied,extra('x43',evidence=[row('owner_approved_refund','TRUE')]))],[('answer','owner_approved_refund','TRUE')])
        # A step that states neither prerequisites nor a cost has none: two such steps for one fact are one way, and under another grant the second is named for the grant alone.
        lean=lambda mid,grant:{'id':mid,'effect':'receipt_filed','provider':'local-provider','grant':grant,'action':'simulate_fact'}
        free=self.parents+[extra('free',methods=[lean('file-free@1','action:file@1')])]
        self.assertEqual((relaxations(free,extra('e6',methods=[lean('file-too@1','action:file@1')])),said(relaxations(free,extra('x44',methods=[lean('file-other@1','action:other@1')])))),
                         ([],[{'kind':'CONDITION_DROPPED','how':'method','method':'file-other@1','effect':'receipt_filed','beside':'file-free@1','dropped':[],'grant':'action:other@1','provider':None,'cheaper':[]}]))
        priced=lambda mid:dict(lean(mid,'action:file@1'),cost={'compute':1})   # beside a way that states no cost one that states a cost costs no less; the other way round it costs less
        self.assertEqual((relaxations(free,extra('e7',methods=[priced('file-paid@1')])),[f['cheaper'] for f in relaxations(self.parents+[extra('priced',methods=[priced('file-priced@1')])],extra('x46',methods=[lean('file-gratis@1','action:file@1')]))]),([],[['compute']]))
        # A new way is named for its grant and for its provider whichever way their names sort beside the parent's.
        also=lambda **kw:relaxations(self.parents,extra('x45',providers={'a-door':1},methods=[m('pay-also@1','refund_paid',['payee_account_checked','owner_approved_refund'],cost={'compute':1,'money':2,'attention':0},**kw)]))
        self.assertEqual(([f['grant'] for f in also(grant='action:zz-pay@1')],[f['provider'] for f in also(grant='action:pay-to-borrower@1',provider='a-door')]),(['action:zz-pay@1'],['a-door']))
        # A fact whose name carries a bar is named whole (the scope is what stands before the first bar).
        barred=[extra('first',scope='lendco/a',evidence=[row('pay|third_party','FALSE',final=True)])]
        self.assertEqual([(f['how'],f['fact'],f['scope']) for f in relaxations(barred,extra('x30',scope='lendco/b'))],[('scope','pay|third_party','lendco/a')])
        # Of two alternatives of the parent that a child's alternative shares as much with, the nearest is the one it loses less of.
        tie=[extra('p',scope='lendco/t',goals=['g'],rules=[r('R@1','g',[['a','b','c'],['a','b']])])]
        self.assertEqual([(f['how'],f['alternative'],f['dropped']) for f in relaxations(tie,extra('x31',rules=[r('R@2','g',[['a']],'R@1')]))],[('rule',1,['b'])])
        # One parent handed in as it is, with a child that relaxes it.
        self.assertEqual([(f['how'],f['replaces'],f['dropped']) for f in relaxations(self.parents[0],extra('x32',rules=[r('R-REFUND@2','refund_settled',[['refund_paid']],'R-REFUND@1')]))],[('rule','R-REFUND@1',['payment_reconciled'])])
        # The check does not know who authored the child: the owner's own yes by decision over the owner's own refusal is named like any other.
        own=extra('x33',evidence=[dict(row('third_party_payout_allowed','TRUE',final=True),source='owner:lendco/servicing')])
        self.assertEqual(said(relaxations(self.parents,own)),[{'kind':'REFUSAL_DROPPED','how':'decision','fact':'third_party_payout_allowed','scope':'lendco/servicing','source':'owner:lendco/servicing'}])
    def test_findings_come_in_one_order(self):
        # Whatever order the packs name things in: refusals by fact, steps by id, grants, asked facts, budget dimensions, providers and cost dimensions by name.
        found=relaxations([pack(n) for n in DESK],extra('x34',scope='lendco/platform'));stated=['may:'+c for c,(tag,_,_) in RULINGS.items() if tag=='never']
        self.assertEqual(([f['fact'] for f in found],sorted(stated)==stated),(sorted(stated),False))   # by fact, which is not the order the desk states them in
        found=relaxations(self.parents,extra('x35',rules=[r('R-RECONCILED@1','payment_reconciled',[['refund_paid']])]))
        self.assertEqual(([(f['kind'],f['how'],f['methods']) for f in found],[i['id'] for i in pack('112_servicing_team')['methods'] if i['effect']=='payment_reconciled']),
                         ([('CONDITION_DROPPED','shadow',['reconcile-by-checker@1','reconcile-by-maker@1'])],['reconcile-by-maker@1','reconcile-by-checker@1']))
        six=['action:%s@1'%n for n in 'fbeadc'];stopped=self.parents+[extra('stop',revoke_grants=six)]
        self.assertEqual([f['grant'] for f in relaxations(stopped,extra('x36',grants=six))],sorted(six))
        facts=['asked_%s'%n for n in 'fbeadc'];asking=[extra('asks',scope='lendco/t',methods=[ask('ask-%s@1'%f,f) for f in facts],providers={'owner-channel':1})]
        self.assertEqual([(f['how'],f['fact']) for f in relaxations(asking,extra('x37',evidence=[row(f,'TRUE') for f in facts]))],[('answer',f) for f in sorted(facts)])
        self.assertEqual([f['dimension'] for f in relaxations(self.parents,extra('x38',budget={'money':11,'compute':11,'attention':4}))],['attention','compute','money'])
        late=self.parents+[extra('late',providers={'a-desk':1})]
        self.assertEqual([f['provider'] for f in relaxations(late,extra('x39',providers={'local-provider':7,'a-desk':2}))],['a-desk','local-provider'])
        dims=list('fbeadc');wide=[extra('wide',scope='lendco/t',budget={d:5 for d in dims},methods=[m('make@1','made',cost={d:1 for d in dims})])]
        self.assertEqual([f['cheaper'] for f in relaxations(wide,extra('x40',methods=[m('make-free@1','made',grant='action:make@1',cost={})]))],[sorted(dims)])
        long=[extra('long',scope='lendco/t',goals=['g'],rules=[r('R@1','g',[dims])],methods=[m('make@1','made',dims)])]   # and the conditions a child drops, of a rule and of a step
        self.assertEqual(([f['dropped'] for f in relaxations(long,extra('x41',rules=[r('R@2','g',[['z']],'R@1')]))],[f['dropped'] for f in relaxations(long,extra('x42',methods=[m('make-bare@1','made',grant='action:make@1')]))]),([sorted(dims)],[sorted(dims)]))
    def test_the_sentence_of_every_way_word_for_word(self):
        stopped=self.parents+[extra('stop',revoke_grants=['action:pay-to-third-party@1'])]
        receipt=self.parents+[extra('receipt',rules=[r('R-REFUND@3','refund_settled',[['source_record_named','refund_paid','payment_reconciled','receipt_filed']],'R-REFUND@2')])]
        one=self.parents+[extra('one-way',methods=[m('file-full@1','receipt_filed',['refund_paid','payment_reconciled','source_record_named'],grant='action:file@1',cost={'compute':2,'money':1,'attention':0})])]
        new=lambda mid,requires,**kw:extra('c',providers={'side-door':1},methods=[m(mid,'refund_paid',requires,**kw)])
        kept=['payee_account_checked','owner_approved_refund'];borrower=dict(grant='action:pay-to-borrower@1',cost={'compute':1,'money':2,'attention':0})
        way='%s is a new way to %s that keeps no way of the parent whole; beside %s it %s'
        for parents,child,lines in (
                (self.parents,extra('c',rules=[r('R-REFUND@3','refund_settled',[['source_record_named','refund_paid','payment_reconciled'],['refund_waived']],'R-REFUND@2')]),
                 ['R-REFUND@3 replaces R-REFUND@2: its alternative 2 keeps no alternative of the parent whole; the nearest loses payment_reconciled, refund_paid, source_record_named']),
                (one,extra('c',providers={'side-door':1},methods=[m('file-early@1','receipt_filed',['refund_paid'],provider='side-door',cost={'compute':1,'money':0,'attention':0})]),
                 [way%('file-early@1','receipt_filed','file-full@1','drops payment_reconciled, source_record_named; is under the grant action:file-early@1, not action:file@1; uses the provider side-door, not local-provider; costs less compute, money')]),
                (self.parents,new('pay-unchecked@1',['owner_approved_refund'],**borrower),[way%('pay-unchecked@1','refund_paid','pay-to-borrower@1','drops payee_account_checked')]),   # each part of that sentence alone:
                (self.parents,new('pay-again@1',kept,cost=borrower['cost']),[way%('pay-again@1','refund_paid','pay-to-borrower@1','is under the grant action:pay-again@1, not action:pay-to-borrower@1')]),   # only what the new way lacks is said
                (self.parents,new('pay-aside@1',kept,provider='side-door',**borrower),[way%('pay-aside@1','refund_paid','pay-to-borrower@1','uses the provider side-door, not local-provider')]),
                (self.parents,new('pay-cheap@1',kept,grant='action:pay-to-borrower@1',cost={'compute':1,'money':0,'attention':0}),[way%('pay-cheap@1','refund_paid','pay-to-borrower@1','costs less money')]),
                (self.parents,extra('c',rules=[r('R-RECONCILED@1','payment_reconciled',[['refund_paid']])]),
                 ['R-RECONCILED@1 puts a rule on payment_reconciled: the kernel then never consults reconcile-by-checker@1, reconcile-by-maker@1, so their prerequisites, grants and costs no longer apply']),
                (receipt,extra('c',rules=[r('R-RECEIPT@1','receipt_filed',[['refund_paid']])]),['R-RECEIPT@1 puts a rule on receipt_filed, a condition the parent leaves to evidence: it can then hold with nothing observed, granted, run or paid']),
                (self.parents,extra('c',evidence=[row('third_party_payout_allowed','TRUE',final=True)]),['the parent refuses third_party_payout_allowed (a FALSE decision in lendco/servicing); the pack replaces it with a TRUE decision']),
                (self.parents,extra('c',scope='lendco/collections',evidence=[row('maker_may_reconcile','FALSE',final=True)]),['the pack moves the scope from lendco/servicing to lendco/collections: the refusal of third_party_payout_allowed stays behind']),
                (stopped,extra('c',grants=['action:pay-to-third-party@1']),['the parent revoked the grant action:pay-to-third-party@1; the pack grants it again']),
                (self.parents,extra('c',methods=[ask('ask-owner-third-party@1','third_party_payout_allowed')]),
                 ['ask-owner-third-party@1 is a method for third_party_payout_allowed, which the parent refuses: it says the refusal more loosely (the kernel will not use it while the decision stands)']),
                (self.parents,extra('c',rules=[r('R-THIRD@1','third_party_payout_allowed',[['refund_due']])]),
                 ['R-THIRD@1 is a rule for third_party_payout_allowed, which the parent refuses: it says the refusal more loosely (the kernel will not use it while the decision stands)']),
                (self.parents,extra('c',evidence=[row('owner_approved_refund','TRUE')]),['the pack carries a TRUE row on owner_approved_refund, which the parent asks about: it answers for the party that was to be asked']),
                (self.parents,extra('c',methods=[m('assume-approval@1','owner_approved_refund')]),['assume-approval@1 is another way to owner_approved_refund, which the parent asks about: the kernel may take it instead of the question']),
                (self.parents,extra('c',rules=[r('R-APPROVED@1','owner_approved_refund',[['refund_due']])]),['R-APPROVED@1 puts a rule on owner_approved_refund, which the parent asks about: the kernel then never asks']),
                (self.parents,extra('c',budget={'money':50}),['the pack raises the budget for money from 10 to 50']),
                (self.parents,extra('c',providers={'owner-channel':5}),['the pack raises the capacity of owner-channel from 1 to 5'])):
            self.assertEqual([f['line'] for f in relaxations(parents,child)],lines)
        self.assertEqual((refusal_of(relaxations,None,extra('c')),refusal_of(verdict,7,extra('c')),refusal_of(install_rule,'112_servicing_team',extra('c'))),('The parents are one pack or a list of packs, in load order',)*3)
        bad=extra('b',budget={'money':-1});self.assertEqual(refusal_of(relaxations,self.parents,bad),'The kernel refuses these packs: '+refusal_of(State.from_packs,self.parents+[bad]))   # the kernel's own words, after the check's
    def test_what_else_the_check_does_not_read(self):
        # Known limits, pinned: each child below relaxes something in effect, the kernel applies it, and the check names nothing.
        # A ceiling is also the balance. A child that states the parents' own ceilings again, number for number, raises nothing the check can see
        # (it compares packs folded from empty); on a State in use the kernel takes the numbers as the new balance: what was spent and the slot
        # the question used come back.
        s=world(PRACTICE);k=Kernel(s);x=k.run_standing(execute=True)['runs'][0];answer(k,x['model_receipts'][-1],'TRUE','owner',execute=True)
        restate=extra('l6',budget={'compute':10,'money':10,'attention':3},providers={'local-provider':6,'owner-channel':1});spent=(dict(s.budget),dict(s.providers));s.apply(restate)
        self.assertEqual((relaxations(self.parents,restate),spent,(s.budget,s.providers)),
                         ([],({'compute':5,'money':8,'attention':2},{'local-provider':2,'owner-channel':0}),({'compute':10,'money':10,'attention':3},{'local-provider':6,'owner-channel':1})))
        # A constructor spec. The lab's own builder packs end with a contract that demands a fourth component, and the candidate fails it; a child
        # that states the spec again with less demanded makes the same candidate pass.
        builder=[pack(n) for n in ('30_build_goal','31_build_theory','32_builder_components','33_bad_constructor')]
        loose=extra('l7',constructors=[dict(builder[3]['constructors'][0],required_effects=['component_validate'])])
        valid=lambda packs:[c['valid_contract'] for c in look(State.from_packs(packs))['candidates']]
        self.assertEqual((relaxations(builder,loose),valid(builder),valid(builder+[loose])),([],[False],[True]))


class RecordLimitTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('independent_verify_for_refusals_limits',ROOT/'qa'/'independent_verify.py')
        self.v=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.v);self.ns={}
        exec(compile((ROOT/'qa'/'checks'/'refusals.py').read_text(),'refusals_checks','exec'),self.ns)   # as the verifier loads it
        self.data=json.loads((ROOT/'results'/'actual_run_records.json').read_text())
    def test_cases_51_to_53_are_what_the_lab_does_again(self):
        # The three cases, made again by the lab and compared whole with the record: every look, every row of every trace, every receipt, the stored state.
        from tools.run_all import scenario
        held={c['id']:c for c in self.data['cases']}
        for cid in ('51_refused_class','52_standing_rules','53_child_relaxes'):
            c=json.loads((ROOT/'cases'/(cid+'.json')).read_text());made=scenario((c['id'],c['title'],c['description'],c['packs'],c['execute'],c['area']))
            self.assertEqual(json.dumps(made,sort_keys=True,ensure_ascii=False),json.dumps(held[cid],sort_keys=True,ensure_ascii=False),cid)
    def test_what_the_independent_checks_leave_unread(self):
        # Known limit, pinned. For the looks of the servicing team and of the review (cases 52 and 53; the blocks yes, no and narrowing of the
        # sequence) the nine claims S60 to S68 read a look's status, actions, pending steps and stop reasons, the methods of its receipts, the
        # question it put, its refused rows, the questions it closed, the packs it loaded and the books after it, and tie proof, needs and
        # branch to rows of its trace. Each change below, alone, leaves all nine passing. What holds these fields is the lab made again: the
        # test above and test_the_recorded_sequence_is_what_the_lab_does_again. (The desk's looks are rebuilt whole by S61 and S62: the controls.)
        files={n:json.loads((ROOT/'scenarios'/(n+'.json')).read_text()) for n in self.ns['NAMES']}
        failed=lambda d:[cid[:3] for cid,ok in self.ns['claims'](d,files,self.v.sha).items() if not ok]
        case=lambda d,cid:[c for c in d['cases'] if c['id']==cid][0];seq=lambda d:d['scenes']['refusals']
        both=lambda d,cid:(case(d,cid)['outcome'],case(d,cid)['run']['runs'][0])   # the two copies the record keeps of a case's first look
        after_yes=lambda d:seq(d)['yes']['answered_yes']['runs'][0];loose=lambda d:seq(d)['narrowing']['loosened']['look']
        rows=lambda x,op:[e['data'] for e in x['trace'] if e['operation']==op]
        self.assertEqual(failed(self.data),[])
        unread=(lambda d:seq(d)['yes']['look']['runs'][0].update(needs=[]),                                  # needs: a look that waits says it needs nothing
                lambda d:seq(d)['no']['look']['runs'][0].update(needs=[]),
                lambda d:after_yes(d)['needs'].reverse(),
                lambda d:loose(d)['runs'][0].update(needs=['refund_paid','payee_account_checked','payment_reconciled']),   # the look that pays the third party says it needed the payee check
                lambda d:seq(d)['yes']['look']['runs'][0]['proof'].reverse(),                                 # the order and the number of the proof lines
                lambda d:[x['proof'].reverse() for x in both(d,'52_standing_rules')],
                lambda d:[seq(d)['no']['look']['runs'][0]['proof'].pop(),loose(d)['runs'][0]['proof'].pop(0)],
                lambda d:loose(d).update(note='reviewed'),                                                    # a key added to a look, and to a run
                lambda d:after_yes(d).update(note='reviewed'),
                lambda d:[x.update(note='reviewed') for x in both(d,'52_standing_rules')],
                lambda d:[x.update(cost={'compute':9,'money':9,'attention':9}) for x in (seq(d)['yes']['look']['runs'][0],seq(d)['no']['look']['runs'][0],after_yes(d),loose(d)['runs'][0])],   # the cost of the four looks of the sequence that wait or ran
                lambda d:after_yes(d)['model_receipts'][0].update(status='PAID_EXTERNALLY'),                  # a receipt's status
                lambda d:[after_yes(d).pop('trace_root_sha256'),seq(d)['no']['answered_no']['runs'][0].pop('trace_root_sha256'),   # the trace root of four runs of the sequence
                          seq(d)['no']['look_again']['runs'][0].pop('trace_root_sha256'),loose(d)['runs'][0].pop('trace_root_sha256')],
                lambda d:[x['model_receipts'][0].update(model_effect='refund_paid') for x in both(d,'52_standing_rules')],   # a receipt's effect, in the look and in its trace
                lambda d:[rows(x,'LOCAL_EFFECT')[0]['receipt'].update(model_effect='refund_paid') for x in both(d,'52_standing_rules')],
                lambda d:[rows(x,'ADMISSION')[-1].update(accepted=False,blockers=['AUTHORITY_REQUIRED']) for x in both(d,'52_standing_rules')],   # what an admission row says
                lambda d:[rows(x,'REFINE')[0].update(rule='R-INSTALL:114_practice_money_movement@pair-000000000000') for x in both(d,'53_child_relaxes')])   # the rule a refine row names
        for i,change in enumerate(unread):
            d=json.loads(json.dumps(self.data));change(d);self.assertNotEqual(d,self.data,i);self.assertEqual(failed(d),[],i)
        read=((lambda d:[x.update(needs=[]) for x in both(d,'52_standing_rules')],'S63'),                     # the controls: the same fields where the checks do read them
              (lambda d:seq(d)['desk']['look']['runs'][5].update(needs=[]),'S62'),
              (lambda d:seq(d)['desk']['look']['runs'][5]['proof'].reverse(),'S62'),
              (lambda d:case(d,'51_refused_class')['run']['runs'][5]['model_receipts'][0].update(model_effect='rate_table_pushed'),'S61'),
              (lambda d:seq(d)['yes']['look']['runs'][0].pop('trace_root_sha256'),'S64'),
              (lambda d:after_yes(d).update(status='WAITING'),'S64'))
        for change,expect in read:
            d=json.loads(json.dumps(self.data));change(d);self.assertIn(expect,failed(d))
    def test_the_check_module_raises_when_a_pack_file_cannot_be_read(self):
        # Known limit, pinned. checks() reads its ten pack files outside any guard: where one is missing, or is no JSON, it raises instead of
        # returning its ten rows as failed. (A verifier that runs the module reports a raise as one failed row named after the file, so the lab
        # still fails; the ids S60 to S69 are then missing from the verdict.) A record that cannot be read is ten failed rows, not a raise.
        class Folder:   # a stand-in for the lab's folder: it reads the lab's files, except one
            def __init__(self,spoiled,parts=()):self.spoiled,self.parts=spoiled,parts
            def __truediv__(self,name):return Folder(self.spoiled,self.parts+(name,))
            def read_text(self,*a,**k):
                if self.parts[-1]=='119_platform_allows_itself.json':
                    if self.spoiled=='missing':raise FileNotFoundError(self.parts[-1])
                    return 'not json'
                return ROOT.joinpath(*self.parts).read_text()
        with self.assertRaises(FileNotFoundError):self.ns['checks'](self.data,Folder('missing'),self.v.sha,self.v.check_chain)
        with self.assertRaises(ValueError):self.ns['checks'](self.data,Folder('no json'),self.v.sha,self.v.check_chain)
        for broken in (None,{},{'cases':[]}):
            got=self.ns['checks'](broken,ROOT,self.v.sha,self.v.check_chain);self.assertEqual(([cid[:3] for cid,_,_ in got],[ok for _,ok,_ in got]),(['S6%d'%i for i in range(10)],[False]*10),repr(broken))


if __name__=='__main__':unittest.main()

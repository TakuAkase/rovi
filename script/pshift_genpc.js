#!/usr/bin/env node

const NS='/rovi/pshift_genpc';
const NScamL='/rovi/cam_l';
const NScamR='/rovi/cam_r';
const NSlive='/rovi/live';
const NSrovi='/rovi';
const ros=require('rosnodejs');
const sensor_msgs=ros.require('sensor_msgs').msg;
const sens=require('../script/ycam1s.js');
const std_msgs=ros.require('std_msgs').msg;
const std_srvs=ros.require('std_srvs').srv;
const rovi_srvs = ros.require('rovi').srv;
const EventEmitter=require('events').EventEmitter;

ros.Time.diff=function(t0){
	let t1=ros.Time.now();
	t1.secs-=t0.secs;
	t1.nsecs-=t0.nsecs;
	return ros.Time.toSeconds(t1);
}

const sensHook=new EventEmitter();
let sensStat=false;
function sensCheck(pub){
	let f=new std_msgs.Bool();
	let b0=sensStat;
	let s;
	try{
		s=sens.stat();
	}
	catch(err){
		sensStat=false;
		console.log('sens not ready');
		setTimeout(function(){ sensCheck(pub);},1000);
		return;
	}
	f.data=true;
	for(let key in s) f.data=f.data && s[key];
	pub.publish(f);
	sensStat=f.data;
	if(!b0 && sensStat) sensHook.emit('start');
	setTimeout(function(){ sensCheck(pub);},1000);
}
function viewOut(n,pubL,capL,pubR,capR){
	try{
//		ros.log.warn('before L');
		if(n<capL.length) pubL.publish(capL[n]);
//		ros.log.warn('after L');
//		ros.log.warn('before R');
		if(n<capR.length) pubR.publish(capR[n]);
//		ros.log.warn('after R');
	}
	catch(err){
		ros.log.warn('No image captured:'+err);
	}
}

setImmediate(async function(){
	const rosNode=await ros.initNode(NS);
	const pub_tat=rosNode.advertise(NS+'/tat', std_msgs.Float32);
	const pub_stat=rosNode.advertise(NS+'/stat', std_msgs.Bool);
	let vue_N=0;

	const raw_L=rosNode.advertise(NScamL+'/image_raw', sensor_msgs.Image);
	const rect_L=rosNode.advertise(NScamL+'/image_rect', sensor_msgs.Image);
	const vue_L=rosNode.advertise(NScamL+'/view', sensor_msgs.Image);
	const remap_L=rosNode.serviceClient(NScamL+'/remap',rovi_srvs.ImageFilter,{persist:true});
	if(! await rosNode.waitForService(remap_L.getService(),2000)){
		ros.log.error('remap_L service not available');
		return;
	}
	const raw_R=rosNode.advertise(NScamR+'/image_raw', sensor_msgs.Image);
	const rect_R=rosNode.advertise(NScamR+'/image_rect', sensor_msgs.Image);
	const vue_R=rosNode.advertise(NScamR+'/view', sensor_msgs.Image);
	const remap_R=rosNode.serviceClient(NScamR+'/remap',rovi_srvs.ImageFilter,{persist:true});
	if(! await rosNode.waitForService(remap_R.getService(),2000)){
		ros.log.error('remap_R service not available');
		return;
	}
	const pub_pc=rosNode.advertise(NSrovi+'/pc', sensor_msgs.PointCloud);
	const genpc=rosNode.serviceClient(NSrovi+'/genpc',rovi_srvs.GenPC,{persist:true});
	if(! await rosNode.waitForService(genpc.getService(),2000)){
		ros.log.error('genpc service not available');
		return;
	}
	let param_L=await rosNode.getParam(NScamL+'/camera');
	let param_R=await rosNode.getParam(NScamR+'/camera');
	let param_P=await rosNode.getParam(NS+'/projector');
	let param_C=await rosNode.getParam(NS+'/camera');
	let param_V=await rosNode.getParam(NSlive+'/camera');

	for(let key in param_C) console.log(NS+'/camera/' + key + "=" + param_C[key]);
	for(let key in param_L) console.log(NScamL+'/camera/' + key + "=" + param_L[key]);
	for(let key in param_R) console.log(NScamR+'/camera/' + key + "=" + param_R[key]);
	for(let key in param_V) console.log(NSlive+'/camera/' + key + "=" + param_V[key]);

	sensHook.on('start',async function(){
ros.log.info('YCAM started');
//		param_V=await rosNode.getParam(NSlive+'/camera');
//		sens.cset(param_V);
//		sens.pset('f'+Math.floor(param_V.AcquisitionFrameRate));
	});
	const sensEv=sens.open(param_L.ID,param_R.ID,param_P.Url,param_P.Port,param_V);//<--------open ycam
	sensEv.on('cam_l',async function(img){//<--------a left eye image comes up
//ros.log.warn('capturing live img_L');
		raw_L.publish(img);
		let req=new rovi_srvs.ImageFilter.Request();
		req.img=img;
		let res=await remap_L.call(req);
ros.log.warn('cam_l/image published');
		if(sensHook.listenerCount('cam_l')>0) sensHook.emit('cam_l',res.img);
		else rect_L.publish(res.img);
	});
	sensEv.on('cam_r',async function(img){//<--------a right eye image comes up
//ros.log.warn('capturing live img_R');
		raw_R.publish(img);
		let req=new rovi_srvs.ImageFilter.Request();
		req.img=img;
		let res=await remap_R.call(req);
ros.log.warn('cam_r/image published');
		if(sensHook.listenerCount('cam_r')>0) sensHook.emit('cam_r',res.img);
		else rect_R.publish(res.img);
	});
	sensCheck(pub_stat);//<--------start checking devices, and output to the topic "stat"

//---------Definition of services
	let capt_L;//<--------captured images of the left camera
	let capt_R;//<--------same as right
	const svc_do=rosNode.advertiseService(NS,std_srvs.Trigger,(req,res)=>{//<--------generate PCL
ros.log.warn('pshift_genpc called!');
		if(!sensStat){
			ros.log.warn('YCAM not ready');
			return false;
		}
		return new Promise(async (resolve)=>{
			param_V=await rosNode.getParam(NSlive+'/camera');
			let fps=Math.floor(param_V.AcquisitionFrameRate);
			param_P=await rosNode.getParam(NS+'/projector');
			let wdt=setTimeout(function(){//<--------watch dog
				resolve(false);
				sensHook.removeAllListeners();
				sens.cset(param_V);
//				sens.pset('f'+fps);
ros.log.warn('in setTimeout');
			},param_P.Interval*20);
//			sens.pset('f0');   //stop trigger
			param_P=await rosNode.getParam(NS+'/projector');
			sens.pset('x'+param_P.ExposureTime);
			let val=param_P.Intencity<256? param_P.Intencity:255;
			val=val.toString(16);
			sens.pset('i'+val+val+val);
			param_C=await rosNode.getParam(NS+'/camera');
			for(let key in param_V) if(!param_C.hasOwnProperty(key)) delete param_V[key];
			sens.cset(param_C);
			sens.pset('p'+param_P.Interval);
			sens.pset('p2');//<--------projector sequence start
			let imgs=await Promise.all([
				new Promise((resolve)=>{
					let capt=[];
					sensHook.on('cam_l',function(img){
ros.log.warn('capturing img_L:'+capt.length);
						if (capt.length <= 11) {
							capt.push(img);
						}
						else if (capt.length == 12) {
							capt.push(img);
							ros.log.warn('now 13 img_Ls. resolve.');
							resolve(capt);
						}
						else { // already capt.length >= 13.
							ros.log.warn('already 13 img_Ls. ignore this img.');
						}
					});
				}),
				new Promise((resolve)=>{
					let capt=[];
//					resolve(capt);
					sensHook.on('cam_r',function(img){
ros.log.warn('capturing img_R:'+capt.length);
						if (capt.length <= 11) {
							capt.push(img);
						}
						else if (capt.length == 12) {
							capt.push(img);
							ros.log.warn('now 13 img_Rs. resolve.');
							resolve(capt);
						}
						else { // already capt.length >= 13.
							ros.log.warn('already 13 img_Rs. ignore this img.');
						}
					});
				})
			]);
ros.log.warn('after await Promise.all');
			sensHook.removeAllListeners();
			clearTimeout(wdt);
			capt_L=imgs[0];
			capt_R=imgs[1];
ros.log.warn('capt_L and capt_R set. capt_L.length=' + capt_L.length + ", capt_R.length=" + capt_R.length);

			ros.log.warn("genpc CALL");
			let gpreq = new rovi_srvs.GenPC.Request();
			gpreq.imgL = capt_L;
			gpreq.imgR = capt_R;
			let gpres=await genpc.call(gpreq);
			pub_pc.publish(gpres.pc);
ros.log.warn('pc published');
			ros.log.warn("genpc DONE");

			sens.cset(Object.assign({'TriggerMode':'Off'},param_V));
			res.message='scan compelete:'+imgs[0].length;
			res.success=true;
ros.log.warn('capture completed');
			viewOut(vue_N,vue_L,capt_L,vue_R,capt_R);
			resolve(true);
		});
	});
	const svc_parse=rosNode.advertiseService(NS+'/parse',rovi_srvs.dialog,(req,res)=>{
		let cmd=req.hello;
		let lbk=cmd.indexOf('{');
		let obj={};
		if(lbk>0){
			cmd=req.hello.substring(0,lbk).trim();
			try {
				obj=JSON.parse(req.hello.substring(lbk));
			}
			catch(err){
				//ignore
			}
		}
		let cmds=cmd.split(' ');
		if(cmds.length>1) cmd=cmds.shift();
		switch(cmd){
		case 'cset':
			sens.cset(obj);
			for(let key in obj){
				ros.log.info('setParam:'+NSlive+'/camera/'+key+'='+obj[key]);
				rosNode.setParam(NSlive+'/camera/'+key,obj[key]);
			}
			return Promise.resolve(true);
		case 'pset':
			sens.pset(cmds[0]);
			return Promise.resolve(true);
		case 'stat'://<--------sensor(maybe YCAM) status query
			return new Promise((resolve)=>{
				res.answer=JSON.stringify(sens.stat());
				resolve(true);
			});
		case 'view':
			return new Promise((resolve)=>{
				vue_N=parseInt(cmds[0]);
ros.log.warn('in view');
if (capt_L === undefined) {
  ros.log.warn('L undefined!!');
}
if (capt_R === undefined) {
  ros.log.warn('R undefined!!');
}
				viewOut(vue_N,vue_L,capt_L,vue_R,capt_R);
				resolve(true);
			});
		}
	});
});

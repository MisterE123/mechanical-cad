"""Fixed visual insertion: transient seed picking, original accepted ownership."""

import bpy
from bpy_extras import view3d_utils

from . import assembly_display, assembly_pending
from . import assembly_joint_overlay as overlay
from . import assembly_joint_viewport as viewport
from .assembly_insert_mate_draft import InsertMateDraft
from .assembly_insert_pick_projection import PickProjection
from .assembly_insert_preview_session import InsertPreviewSession
from .bridge import BridgeError


def _draw_target(owner):
    if not owner.draw_context() or owner.phase != 'picking' or not owner.target_points:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    with overlay.drawing_state():
        gpu.state.depth_test_set('NONE' if owner.target_only else 'LESS_EQUAL')
        if owner.target_batch is None:
            owner.target_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            owner.target_batch = batch_for_shader(owner.target_shader, 'TRIS', {'pos':owner.target_points})
        owner.target_shader.bind()
        owner.target_shader.uniform_float('color',(0.1,0.75,1.0,0.45))
        owner.target_batch.draw(owner.target_shader)


class InsertMateSession(InsertPreviewSession):
    title = 'Insert + mate · not saved / checked'
    header = 'Visual insertion · pick Parent / New child · explicit Apply inserts both'

    def __init__(self, context, draft):
        super().__init__(context,draft)
        joint = next(j for j in draft.candidate()['joints'] if j['id']==draft.joint_id)
        if joint['kind'] != 'fixed':
            raise BridgeError('Visual insertion currently supports fixed joints only.')
        self.names = {i["id"]:i["name"] for i in draft.candidate()["instances"]}
        self.parent_id = joint['parent']
        self.child_id = draft.instance_id
        self.phase = 'seed'
        self.mate = self.projection = None
        self.seed_ghost = ()
        self.pick_end = 'parent'
        self.faces = {'parent':None,'child':None}
        self.target_only = False
        self.target_points = ()
        self.target_batch = self.target_shader = None
        self.rv3d = self.area.spaces.active.region_3d
        if self.rv3d is None or self.area.spaces.active.region_quadviews:
            raise BridgeError('Visual insertion requires a standard single 3D viewport, not Quad View.')
        self.accepted_objects = frozenset(assembly_display.owned_objects(
            self.scene,self.snapshot['fields']['owner_id']))

    def assert_current(self, context):
        super().assert_current(context)
        if (self.area.spaces.active.region_quadviews
                or self.area.spaces.active.region_3d != self.rv3d
                or frozenset(assembly_display.owned_objects(
                    self.scene,self.snapshot['fields']['owner_id'])) != self.accepted_objects):
            raise BridgeError('The accepted display or picking viewport changed. Reopen Insert.')

    def start(self, context):
        super().start(context)
        try:
            self.handlers.append(bpy.types.SpaceView3D.draw_handler_add(
                _draw_target,(self,),'WINDOW','POST_VIEW'))
            return self
        except Exception:
            self.cancel('Could not start insertion target highlight')
            raise

    def _show_response(self, response):
        super()._show_response(response)
        if self.phase == 'seed':
            self.mate = InsertMateDraft(self.draft,response)
            self.projection = PickProjection(response,self.expectation,self.draft.candidate())
            self.seed_ghost = self.ghost_positions
            self.phase = 'picking'
            self.expectation = None
            self.select_end('parent')
        elif self.phase == 'final_pending':
            self.phase = 'final'
            self.target_only = False
            self.target_points = ()
            self.target_batch = None
            self.message = 'Face mate ready · explicit Apply inserts child + joint'
        else:
            raise BridgeError('Unexpected insertion picking replay state.')

    def ready(self):
        return self.phase == 'final' and super().ready()

    def select_end(self, end):
        if end not in ('parent','child') or self.pending is not None:
            raise BridgeError('Wait for the current insertion replay before picking.')
        self.expectation = None
        self.phase = 'picking'
        self.pick_end = end
        self.target_only = False
        self.ghost_positions = self.seed_ghost
        identifier = self.parent_id if end=='parent' else self.child_id
        vertices,triangles = self.projection.target_geometry(identifier)
        self.target_points = tuple(tuple(value*self.scale for value in vertices[index])
                                   for triangle in triangles for index in triangle)
        self.target_batch = None
        self.message = 'Pick a planar face on highlighted ' + ('Parent' if end=='parent' else 'New child')
        self.error = ''

    def _foreign_occlusion(self, context, origin, direction, distance_mm):
        obj = viewport._nearest_visible_mesh(self.view_layer,self.area.spaces.active,
                context.evaluated_depsgraph_get(),origin,direction,exclude_objects=self.accepted_objects)
        if obj is None:
            return
        # Accepted identities are captured references and revalidated above;
        # copied tags never make a foreign object part of that identity set.
        evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
        matrix = evaluated.matrix_world.copy()
        inverse = matrix.inverted()
        hit,location,_normal,_index = evaluated.ray_cast(
            inverse@origin,(inverse.to_3x3()@direction).normalized())
        if not hit:
            raise BridgeError('Visible surface changed during picking. Pick again.')
        distance = ((matrix@location)-origin).dot(direction.normalized())/self.scale
        if distance <= distance_mm + 1e-7 + abs(distance_mm)*1e-12:
            raise BridgeError('Another visible object obscures this face. Rotate the view or explicitly pick highlighted only.')

    def pick(self, context, point):
        if self.phase != 'picking' or self.pending is not None:
            return
        self.expectation = None
        self.assert_current(context)
        identifier = self.parent_id if self.pick_end=='parent' else self.child_id
        origin = view3d_utils.region_2d_to_origin_3d(self.region,self.rv3d,point)
        direction = view3d_utils.region_2d_to_vector_3d(self.region,self.rv3d,point)
        hit = self.projection.pick(identifier,[v/self.scale for v in origin],list(direction),
                                   target_only=self.target_only)
        if hit is None:
            raise BridgeError('No face on the named highlighted component under the pointer.')
        if not self.target_only:
            self._foreign_occlusion(context,origin,direction,hit['distance_mm'])
        proposed = dict(self.faces)
        proposed[self.pick_end] = hit['face_id']
        if all(proposed.values()):
            self.mate.attach_face_pair(proposed['parent'],proposed['child'])
            self.faces = proposed
            self.candidate = self.mate.candidate()
            self.target_points = ()
            self.target_batch = None
            self.phase = 'final_pending'
            self.message = 'Replaying complete face-mated insertion · nothing saved'
            self.pending = assembly_pending.prepare_insert_mate_preview(
                context,self.mate,expected_json=self.snapshot['fields']['document_json'],
                expected_working_part=self.snapshot['working_part'])
        else:
            self.faces = proposed
            self.select_end('child' if self.pick_end=='parent' else 'parent')

    def cancel(self, reason='Visual insertion cancelled'):
        self.target_points = ()
        self.target_batch = self.target_shader = None
        self.projection = self.mate = None
        super().cancel(reason)

    def panel_layout(self):
        left,bottom,right,top = viewport._safe_rect(self)
        scale = min(self.ui_scale,(right-left)/390,(top-bottom)/410)
        if scale < 1:
            return overlay.build_panel((left,bottom,right,top),scale=1)
        x,y = left+10*scale,bottom+382*scale
        text = [self.title,self.revisions,'Parent: '+self.names[self.parent_id],'New child: '+self.names[self.child_id],
                'Parent face: '+(self.faces['parent'] or 'not picked'),
                'Child face: '+(self.faces['child'] or 'not picked'),
                ('Full Assembly geometry + mate preview' if self.phase in ('final','final_pending')
                 else 'HIGHLIGHTED ONLY: other geometry ignored' if self.target_only
                 else 'Visible nearest surfaces only'),
                self.message,self.error]
        labels=[]
        for line in text:
            if line:
                labels.append(overlay.Label(line,(x,y),overlay.GOLD if not labels else overlay.TEXT,line))
                y-=20*scale
        def button(action,label,tip,x0,y0,width,enabled=True):
            return overlay.Button(action,label,tip,(x+x0*scale,bottom+y0*scale,
                x+(x0+width)*scale,bottom+(y0+30)*scale),enabled=enabled)
        picking=self.phase=='picking' and self.pending is None
        buttons=(
            button('parent','Pick Parent','Pick the named Parent on the original seed',0,130,175,picking),
            button('child','Pick New child','Pick the new child on the original seed',180,130,180,picking),
            button('target_only','Highlighted only: '+('ON' if self.target_only else 'OFF'),
                   'Explicit target-only picking ignores all other geometry; target nearest face stays strict',0,92,360,picking),
            button('restart','Restart face picks','Restore seed preview and discard face picks, not accepted geometry',0,54,360,self.projection is not None and self.pending is None),
            button('apply','Insert face-mated child','Freshly replay and atomically insert this exact candidate',0,10,230,self.ready()),
            button('cancel','Cancel / Esc','Keep accepted Assembly unchanged',235,10,125),
        )
        return overlay.Panel((left,bottom,left+390*scale,bottom+410*scale),buttons,tuple(labels),scale,12*scale)

    def modal_event(self, operator, context, event):
        if not self.alive:
            return {'FINISHED'} if self.finished else {'CANCELLED'}
        if not self.light_binding(context):
            self.cancel('Visual insertion context changed')
            return {'CANCELLED'}
        if event.value=='PRESS' and (event.type=='ESC' or event.type=='Z' and event.ctrl):
            self.cancel()
            return {'CANCELLED','PASS_THROUGH'} if event.type=='Z' else {'CANCELLED'}
        try:
            if event.type=='TIMER':
                self.tick(context)
            elif event.type in viewport.NAVIGATION_EVENTS:
                return {'PASS_THROUGH'}
            else:
                point=viewport._screen_xy(self,event)
                panel=self.panel_layout()
                button=overlay.hit_button(panel,point)
                if event.type=='MOUSEMOVE':
                    self.hover=button.action if button else ''
                    self.hint=overlay.hint_at(panel,point)
                if event.type=='LEFTMOUSE' and event.value=='PRESS':
                    if button and button.enabled:
                        action=button.action
                        if action=='cancel':
                            self.cancel()
                        elif action=='apply':
                            self.apply(context)
                        elif action in ('parent','child'):
                            self.select_end(action)
                        elif action=='target_only':
                            self.target_only=not self.target_only
                        elif action=='restart':
                            self.faces={'parent':None,'child':None}
                            self.select_end('parent')
                    elif not button and not (panel.bounds[0]<=point[0]<=panel.bounds[2]
                                              and panel.bounds[1]<=point[1]<=panel.bounds[3]):
                        self.pick(context,point)
                self.area.tag_redraw()
        except Exception as exc:
            self.error=str(exc)
            self.expectation=None
            self.message='Pick refused · accepted Assembly retained'
            # Context invalidation closes rather than retaining a stale session.
            try:
                self.assert_current(context)
            except Exception:
                self.cancel(str(exc))
                operator.report({'WARNING'},str(exc))
        return {'RUNNING_MODAL'} if self.alive else ({'FINISHED'} if self.finished else {'CANCELLED'})

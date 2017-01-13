
import re
import math
import random

# if (when) this doesn't work, copy 64 bit Python 3.3 fbx.pyd and fbxsip.pyd from the Autodesk FBX SDK
# into this directory
import fbx

# FbxDouble3 unpacker
def tolist(x):
  return [x[i] for i in range(3)]

# FbxDouble3 packer
def tovec3(x):
  return fbx.FbxDouble3(x[0], x[1], x[2], x[3])

def add3(x, y):
  return [x[i]+y[i] for i in range(3)]

def sub3(x, y):
  return [x[i]-y[i] for i in range(3)]

def neg3(x):
  return [-x[i] for i in range(3)]

def xy_location(x):
  return (round(x[0]), round(x[1]))

def rotateZ(v, angle):
  sz = math.sin(angle * (3.14159/180))
  cz = math.cos(angle * (3.14159/180))
  return [
    cz * v[0] - sz * v[1],
    sz * v[0] + cz * v[1],
    v[2]
  ]

def lim360(x):
  x = x + 360 if x < 0 else x
  x = x - 360 if x >= 360 else x
  return round(x)

class dungeon_generator:
  def __init__(self):  
    self.sdk_manager = fbx.FbxManager.Create()
    if not self.sdk_manager:
      sys.exit(1)
    
    self.io_settings = fbx.FbxIOSettings.Create(self.sdk_manager, fbx.IOSROOT)
    self.sdk_manager.SetIOSettings(self.io_settings)

  def read_components(self):
    importer = fbx.FbxImporter.Create(self.sdk_manager, "")    
    result = importer.Initialize("scenes/components.fbx", -1, self.io_settings)
    if not result:
      raise BaseException("could not find components file")
    self.components = fbx.FbxScene.Create(self.sdk_manager, "")
    result = importer.Import(self.components)
    importer.Destroy()

    root = self.components.GetRootNode()
    top_level = [root.GetChild(i) for i in range(root.GetChildCount())]

    # child nodes matching this pattern are feature markup
    feature_pattern = re.compile('(\<|\>)([^.]+)(\..*)?')

    incoming = self.incoming = {}
    outgoing = self.outgoing = {}
    tiles = self.tiles = {}

    # find the tiles in the file with at least one child (the connectors)
    for node in top_level:
      if node.GetChildCount():
        # for each tile, check the names of the connectors
        tiles[node.GetName()] = node;
        connectors = [node.GetChild(i) for i in range(node.GetChildCount())]
        tile_name = node.GetName()
        print("%s has %d children" % (tile_name, node.GetChildCount()))
        for c in connectors:
          conn_name = c.GetName();
          # use a regular expression to match the connector name
          # and discard any trailing numbers
          match = feature_pattern.match(conn_name)
          if match:
            direction = match.group(1)
            feature_name = match.group(2)
            print("  %s %s %s" % (tile_name, direction, feature_name))
            trans = c.LclTranslation.Get()
            rot = c.LclRotation.Get()
            result = (feature_name, tile_name, trans, rot)

            if direction == '>':
              # outgoing tile indexed by tile_name
              idx = tile_name
              dict = outgoing
            else:
              # incoming tile indexed by feature name
              idx = feature_name
              dict = incoming
            if not idx in dict:
              dict[idx] = []
            dict[idx].append(result)

    # at this point incoming and outgoing index connectors
    # tiles indexes the tiles by name.
    print("self.incoming:", self.incoming)
    print("self.outgoing:", self.outgoing)

  def get_format(self, name):
    reg = self.sdk_manager.GetIOPluginRegistry()
    for idx in range(reg.GetWriterFormatCount()):
      desc = reg.GetWriterFormatDescription(idx)
      print(desc)
      if name in desc:
        return idx
    return -1

  def write_result(self):
    #format = self.get_format("FBX binary")
    format = self.get_format("FBX ascii")

    new_scene = fbx.FbxScene.Create(self.sdk_manager, "result");
    self.create_dungeon(new_scene, "flat")

    exporter = fbx.FbxExporter.Create(self.sdk_manager, "")
    
    if exporter.Initialize("scenes/result.fbx", format, self.io_settings):
      exporter.Export(new_scene)

    exporter.Destroy()

  def make_node(self, new_scene, node_name, pos, angle):
    dest_node = fbx.FbxNode.Create( new_scene, node_name )
    dest_node.SetNodeAttribute(self.tile_meshes[node_name])
    dest_node.LclTranslation.Set(fbx.FbxDouble3(pos[0], pos[1], pos[2]))
    dest_node.LclRotation.Set(fbx.FbxDouble3(0, 0, angle))
    root = new_scene.GetRootNode()
    root.AddChild(dest_node)

  def try_tile(self, new_scene, todo, edges, pos, angle, incoming, in_sel):
    in_feature_name, in_tile_name, in_trans, in_rot = incoming[in_sel]

    # from the feature, set the position and rotation of the new tile
    new_angle = lim360(angle - in_rot[2])
    tile_pos = add3(pos, rotateZ(neg3(in_trans), new_angle))
    tile_name = in_tile_name
    print(tile_pos, new_angle, tile_name)

    # outgoing features are indexed on the tile name
    outgoing = self.outgoing[tile_name]

    # check existing edges to see if this tile fits.
    # although we know that one edge fits, we haven't checked the others.
    for out_sel in range(len(outgoing)):
      out_feature_name, out_tile_name, out_trans, out_rot = outgoing[out_sel]
      new_pos = add3(tile_pos, rotateZ(out_trans, new_angle))
      if xy_location(new_pos) in edges:
        edge_pos, edge_angle, edge_feature_name, edge_satisfied = edges[xy_location(new_pos)]
        print("check", new_pos, edge_pos, out_feature_name, edge_feature_name, edge_satisfied)
        if edge_satisfied:
          return False
        # check the height of the join.
        # note: we should also check that the incoming matches the outgoing.
        if abs(edge_pos[2] - new_pos[2]) > 0.01:
          print("fail")
          return False

    # add all outgoing edges to the todo list and mark edges
    # note: if there were multiple outgoing edge choices, we would have to select them.
    for out_sel in range(len(outgoing)):
      out_feature_name, out_tile_name, out_trans, out_rot = outgoing[out_sel]
      new_pos = add3(tile_pos, rotateZ(out_trans, new_angle))
      if not xy_location(new_pos) in edges:
        # make an unsatisfied edge
        edge = (new_pos, lim360(new_angle + out_rot[2]), out_feature_name, None)
        edges[xy_location(new_pos)] = edge
        todo.append(edge)
      else:
        edge_pos, edge_angle, edge_feature_name, edge_satisfied = edges[xy_location(new_pos)]
        edges[xy_location(new_pos)] = (edge_pos, edge_angle, edge_feature_name, out_feature_name)

    self.make_node(new_scene, tile_name, tile_pos, new_angle)
    print("pass")
    return True

  #def create_room(self, new_scene, feature_name):


  def create_dungeon(self, new_scene, feature_name):
    # clone the tile meshes and name them after their original nodes.
    tile_meshes = self.tile_meshes = {}
    for name in self.tiles:
      tile = self.tiles[name]
      tile_mesh = tile.GetNodeAttribute()
      tile_meshes[name] = tile_mesh.Clone(fbx.FbxObject.eDeepClone, None)
      tile_meshes[name].SetName(name)

    edges = {}
    pos = (0, 0, 0)
    angle = 0

    # create an unsatisfied edge
    todo = [(pos, angle, feature_name, False)]
    num_tiles = 0
    random.seed()

    # this loop processes one edge from the todo list.
    while len(todo) and num_tiles < 100:
      pos, angle, out_feature_name, in_feature_name = todo.pop()

      print(xy_location(pos))

      for i in range(4):
        # incoming features are indexed on the feature name
        incoming = self.incoming[out_feature_name]
        in_sel = int(random.randrange(len(incoming)))

        if self.try_tile(new_scene, todo, edges, pos, angle, incoming, in_sel):
          break

      num_tiles += 1

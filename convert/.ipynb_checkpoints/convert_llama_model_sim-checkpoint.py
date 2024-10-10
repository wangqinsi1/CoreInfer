import torch.nn as nn
import gc
from scipy.stats import norm
import torch
import numpy as np
import pickle
from sklearn.preprocessing import MultiLabelBinarizer
from tqdm import tqdm
import pickle
import os
global_cluster = None


class DownLayer(nn.Module):
    def __init__(self, weight, act_list, num, kmeans, mlb_loaded, sparsity, memory_limit,name = None):
        super(DownLayer, self).__init__()
        self.weight = weight.clone()
        remained_neurons = int(weight.size(1) * sparsity)
        self.remained_neurons = remained_neurons
        self.memory_limit = memory_limit
        if memory_limit:
            self.filtered_W = torch.zeros((weight.size(0),remained_neurons)).to(torch.float16).cpu()
        else:
            self.filtered_W = torch.zeros((weight.size(0),remained_neurons)).to(torch.float16).cuda()
        self.act_list = act_list[:][:remained_neurons]
        self.num = num
        self.kmeans = kmeans
        self.mlb_loaded=mlb_loaded
        self.weight_updated = False
        
    def forward(self, x):
        if x.size(1)>1:
            self.weight_updated = False
            self.weight = self.weight.cuda()
            true_value = x @ self.weight.T.cuda()
            
            x1=x.clone()
            if self.num == 25:
                sorted_values, sorted_indices = torch.sort(x1, dim=1, descending=True)
                limit=int(0.4*(x1>0).sum().item()/x1.size(0))
                top_indices = sorted_indices[:, :limit]
                data_flattened = top_indices.reshape(-1)
                unique_numbers, counts = data_flattened.unique(return_counts=True, sorted=True)
                sorted_indices = torch.argsort(counts, descending=True)
                sorted_indices_clu = unique_numbers[sorted_indices]
                
                indices_all = sorted_indices_clu[:3000].cpu().numpy()
                indices_all_2d = [indices_all.tolist()]
                new_data = self.mlb_loaded.transform(indices_all_2d)
                
                predictions = self.kmeans.predict(new_data)
                if self.memory_limit:
                    self.weight = self.weight.cpu()
                global global_cluster
                global_cluster = predictions[0]
                del indices_all_2d, new_data
                gc.collect()
            
        
            
        else:
            if not self.weight_updated:
                cluster_num = global_cluster
                activated_list = self.act_list[cluster_num].tolist()
                self.filtered_W = self.weight[:, activated_list].clone().cuda()
                if self.memory_limit:
                    self.weight = self.weight.cpu()
                self.weight_updated = True

            true_value = x @ self.filtered_W.T.cuda()
            
        return true_value



class UpLayer(nn.Module):
    def __init__(self, weight, act_list, sparsity, memory_limit, name = None):
        super(UpLayer, self).__init__()
        self.weight = weight.clone()
        remained_neurons = int(weight.size(0) * sparsity)
        self.remained_neurons = remained_neurons
        self.memory_limit = memory_limit
        if memory_limit:
            self.filtered_W = torch.zeros((remained_neurons,weight.size(1))).to(torch.float16).cpu()
        else:
            self.filtered_W = torch.zeros((remained_neurons,weight.size(1))).to(torch.float16).cuda()
        self.act_list = act_list[:remained_neurons]
        self.weight_updated = False
        
    def forward(self, x):
        if x.size(1)>1:
            self.weight_updated = False
            self.weight = self.weight.cuda()
            true_value = x @ self.weight.T
            if self.memory_limit:
                self.weight = self.weight.cpu()

        else:
            if not self.weight_updated:
                cluster_num = global_cluster
                activated_list = self.act_list[cluster_num].tolist()
                self.filtered_W = self.weight[activated_list,:].clone().cuda()
                if self.memory_limit:
                    self.weight = self.weight.cpu()
                self.weight_updated = True
            
            true_value = x @ self.filtered_W.T.cuda()
            
        return true_value


class GateLayer(nn.Module):
    def __init__(self, weight, act_list, sparsity, memory_limit, name = None):
        super(GateLayer, self).__init__()
        self.weight = weight.clone().cuda()
        remained_neurons = int(weight.size(0) * sparsity)
        self.remained_neurons = remained_neurons
        self.memory_limit = memory_limit
        if memory_limit:
            self.filtered_W = torch.zeros((remained_neurons, weight.size(1))).to(torch.float16).cpu()
        else:
            self.filtered_W = torch.zeros((remained_neurons, weight.size(1))).to(torch.float16).cuda()
        self.act_list = act_list[:remained_neurons]
        self.weight_updated = False
        
    def forward(self, x):
        if x.size(1)>1:
            self.weight_updated = False
            self.weight = self.weight.cuda()
            true_value = x @ self.weight.T
            if self.memory_limit:
                self.weight = self.weight.cpu()

        else:
            if not self.weight_updated:
                cluster_num = global_cluster
                activated_list = self.act_list[cluster_num].tolist()
                self.filtered_W = self.weight[activated_list,:].clone().cuda()
                if self.memory_limit:
                    self.weight = self.weight.cpu()
                self.weight_updated = True
            
            true_value = x @ self.filtered_W.T.cuda()
            
        return true_value





def convert_llama_model_sim(model, num_layers, sparsity, start_num, end_num, memory_limit, cluster_path):
    
    with open(f'{cluster_path}/cluster_activation/kmeans.pkl', 'rb') as f:
        kmeans = pickle.load(f)

    with open(f'{cluster_path}/cluster_activation/mlb_model.pkl', 'rb') as file:
        mlb_loaded = pickle.load(file)
        
    Predictor=[]
    
    cluster_num = 0
    for root, dirs, files in os.walk(f'{cluster_path}/neuron_activation/0'):
        cluster_num += len(files)
        
    for i in range(num_layers):
        predict_layer=[]
        for cluster_catagory in range(0,cluster_num):
            with open(f'{cluster_path}/neuron_activation/{i}/cluster_{cluster_catagory}.pkl', 'rb') as f:
                    model_predictor = pickle.load(f)
            predict_layer.append(model_predictor)
        Predictor.append(predict_layer)
    
    
    for name, module in tqdm(model.named_modules(), desc="Convert Llama Models"):
        if "down" in name:
            num=int(name.split('.')[2])
            if num>start_num and num<end_num:
                parent_name = name.rsplit('.', 1)[0] if '.' in name else ''
                attr_name = name.rsplit('.', 1)[-1]
                if parent_name != '':
                    parent = dict(model.named_modules())[parent_name]
                else:
                    parent = model
                    
                NewLayer = DownLayer(module.weight, Predictor[num], num, kmeans, mlb_loaded, sparsity, memory_limit, name = name)
                setattr(parent, attr_name, NewLayer)
                del module
                
        elif "up" in name:
            num=int(name.split('.')[2])
            if num>start_num and num<end_num:
                parent_name = name.rsplit('.', 1)[0] if '.' in name else ''
                attr_name = name.rsplit('.', 1)[-1]
                if parent_name != '':
                    parent = dict(model.named_modules())[parent_name]
                else:
                    parent = model
                    
                NewLayer = UpLayer(module.weight, Predictor[num], sparsity, memory_limit, name = name)
                setattr(parent, attr_name, NewLayer)
                del module

        
        elif "gate" in name:
            num=int(name.split('.')[2])
            if num>start_num and num<end_num:
                parent_name = name.rsplit('.', 1)[0] if '.' in name else ''
                attr_name = name.rsplit('.', 1)[-1]
                if parent_name != '':
                    parent = dict(model.named_modules())[parent_name]
                else:
                    parent = model
                    
                NewLayer = GateLayer(module.weight, Predictor[num], sparsity, memory_limit, name = name)
                setattr(parent, attr_name, NewLayer)
                del module
    
    gc.collect()
    print("Converted Model Done")
    
    return model
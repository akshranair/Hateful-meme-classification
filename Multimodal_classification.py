# -*- coding: utf-8 -*-
"""Q4.c.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/12UbSwJkJ10GkRGeXjZByUgvq6FVA5lvD
"""

from google.colab import drive
drive.mount('/content/drive')

!pip install transformers

import nltk
nltk.download('stopwords')

import pandas as pd
import re
import torch
import nltk
from nltk.corpus import stopwords
import numpy as np

import os
import json
import pickle

import shutil
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder

from tqdm import tqdm
from transformers import *
from transformers import TFDistilBertModel,DistilBertTokenizer,DistilBertConfig

stopwords = set(stopwords.words('english'))
import warnings
warnings.filterwarnings('ignore')

import torchvision.transforms as transforms
from PIL import Image
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, models

from torchvision import models

P = '/content/drive/MyDrive/ak/hateful_memes/train.jsonl'
D = '/content/drive/MyDrive/ak/hateful_memes/dev_seen.jsonl'
T = '/content/drive/MyDrive/ak/hateful_memes/test_seen.jsonl'

train = pd.read_json(P, lines = True)
dev = pd.read_json(D,lines = True)
test = pd.read_json(T, lines = True)

main_path = '/content/drive/MyDrive/ak/hateful_memes/'

device = 'cuda'

with open('train.pkl', 'rb') as f:
    data = pickle.load(f)



with open('train.pkl', 'wb') as f:
    pickle.dump(train, f)

with open('dev.pkl', 'wb') as f:
    pickle.dump(dev, f)

with open('test.pkl', 'wb') as f:
    pickle.dump(test, f)

with open('train.pkl', 'rb') as f:
    train = pickle.load(f)

with open('dev.pkl', 'rb') as f:
    dev = pickle.load(f)

with open('test.pkl', 'rb') as f:
    test = pickle.load(f)

def Preprocess(dataset,column,label):
  Data = pd.DataFrame(columns = ['text', 'label']);
  # Data['text'] = data[column]
  Data['label'] = dataset[label]
  Data['id'] = dataset['id']
  clean_text = []
  maxlen = 0
  words_set = set()
  for i in dataset[column]:
    text = i
    text = re.sub(r'<.*?>',' ',text)#removing anchor html tags
    text = re.sub(r'[^A-Za-z0-9\s]',' ',text) #removing speacial characters
    text = re.sub(r'\s+',' ',text)#removing extra space
    text = text.lower()#lowercasing
    tokens = text.split(' ')
    clean_tokens = []
    for token in tokens:
      if(token not in stopwords):#removing stopwords
        clean_tokens.append(token)
      words_set.add(token)
      
    maxlen = max(maxlen, len(clean_tokens))
    txt = ' '.join(clean_tokens)
    clean_text.append(txt)
  Data['text']  = clean_text
  vocab_size = len(words_set)
  
  return Data,maxlen, vocab_size

ct,max_len,vocab_size =Preprocess(train,'text','label')
df_dev, max_len_dev, vocab_size_dev= Preprocess(dev,'text', 'label')
df_test, max_len_test, vocab_size_test= Preprocess(test,'text', 'label')

class Custom_Dataset():
    def __init__(self, data,sentences,labels,transforms=None):
        self.data = data
        self.labels = labels
        self.transforms = transforms
        self.sentences = sentences
        self.dbert_tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-uncased')
        self.input_ids = []
        self.attention_masks=[]
        max_len = 128
        for sent in self.sentences:
          dbert_inps = self.dbert_tokenizer.encode_plus(sent,add_special_tokens = True,max_length =max_len,pad_to_max_length = True,return_attention_mask = True,truncation=True)
          self.input_ids.append(dbert_inps['input_ids'])
          self.attention_masks.append(dbert_inps['attention_mask'])
        self.input_ids = np.asarray(self.input_ids)
        self.attention_masks = np.asarray(self.attention_masks)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        image_path = self.data[index]
        label = self.labels[index]
        image = Image.open(main_path + image_path).convert('RGB')
        if self.transforms:
            image = self.transforms(image)
        id = self.input_ids[index]
        am = self.attention_masks[index]
        return id,am,image,label

train_transforms = transforms.Compose([
    transforms.Resize((224,224)),
    transforms.RandomHorizontalFlip(),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])



train_dataset = Custom_Dataset(train['img'],ct['text'],train['label'], transforms=train_transforms)
train_loader = DataLoader(train_dataset, batch_size=32, shuffle=False)
dev_dataset = Custom_Dataset(dev['img'],df_dev['text'],dev['label'], transforms=train_transforms)
dev_loader = DataLoader(dev_dataset, batch_size=32, shuffle=False)
test_dataset = Custom_Dataset(test['img'],df_test['text'],test['label'], transforms=train_transforms)
test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False)

class Multimodal(nn.Module):
  def __init__(self):
    super(Multimodal,self).__init__()
    self.image_model = models.resnet50(pretrained = True)
    self.image_model_dim = self.image_model.fc.in_features
    for param in self.image_model.parameters():
      param.requires_grad = False
    self.image_model.fc = nn.Identity()
    self.language_model = DistilBertModel.from_pretrained('distilbert-base-uncased')
    self.dense = nn.Linear(self.image_model_dim + self.language_model.config.dim, 512)
    self.relu = nn.ReLU()
    self.dropout = nn.Dropout(0.5)
    self.fc = nn.Linear(512,2)
    self.softmax = nn.Softmax()

  def forward(self, img, input_ids, attention_mask):
    output_image = self.image_model(img)
    output_text = self.language_model(input_ids = input_ids, attention_mask = attention_mask)
    output_text = output_text[0][:,0,:]
    combined = torch.cat((output_image, output_text), dim = 1)
    combined = self.dense(combined)
    combined = self.relu(combined)
    combined = self.dropout(combined)
    output = self.fc(combined)
    output = self.softmax(output)
    return output

  def get_features(self, img, input_ids, attention_mask):
    with torch.no_grad():
      output_image = self.image_model(img)
      output_text = self.language_model(input_ids=input_ids, attention_mask=attention_mask)
      output_text = output_text[0][:,0,:]
      combined = torch.cat((output_image, output_text), dim=1)
      features = self.dense(combined)
      features = self.relu(features)
      features = self.dropout(features)
    return features

model = Multimodal()
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(),lr =3e-5,weight_decay = 0.01)

train_losses = []
validation_losses=[]
train_accuracy=[]
val_accuracy = []
for epoch in range(5):
  train_loss = 0
  correct_train = 0
  val_loss = 0
  correct_val = 0
  total_train=0
  total_val=0
  model.train()
  for batch in tqdm(train_loader):
    optimizer.zero_grad()
    id = batch[0].to(device)
    am = batch[1].to(device)
    im = batch[2].to(device)
    lbl = batch[3].to(device)
    model = model.to(device)
    output = model(im,id,am)
    loss = criterion(output,lbl)
    loss.backward()
    optimizer.step()
    train_loss+=loss.item()
  train_losses.append(train_loss)
  
  model.eval()
  with torch.no_grad():
    for batch in tqdm(train_loader):
      id = batch[0].to(device)
      am = batch[1].to(device)
      im = batch[2].to(device)
      lbl = batch[3].to(device)
      otp = model(im,id,am)
      _,pred = otp.max(1)
      correct_train+=pred.eq(lbl).sum().item()
      total_train+=lbl.size(0)
  accuracy = 100*(correct_train/total_train)
  train_accuracy.append(accuracy)

  with torch.no_grad():
    for batch in tqdm(dev_loader):
      id = batch[0].to(device)
      am = batch[1].to(device)
      im = batch[2].to(device)
      lbl = batch[3].to(device)
      otps = model(im, id, am)
      lss = criterion(otps,lbl)
      val_loss+=lss.item()
      _,predictions = otps.max(1)
      correct_val+=predictions.eq(lbl).sum().item()
      total_val+=lbl.size(0)
    acc = 100*(correct_val/total_val)
    val_accuracy.append(acc)
    validation_losses.append(val_loss)

import matplotlib.pyplot as plt
import numpy as np
x = np.arange(5)
plt.plot(x,train_losses,label = 'train_loss')
plt.plot(x,validation_losses,label = 'validation loss')
plt.legend()
plt.title("Epoch Vs Loss")
plt.xlabel('epochs')
plt.ylabel('loss')
plt.show()

x = np.arange(5)
plt.plot(x,train_accuracy,label = 'train accuracy')
plt.plot(x,val_accuracy,label = 'validation accuracy')
plt.legend()
plt.xlabel('epochs')
plt.ylabel('accuracy')
plt.title("Epoch Vs Accuracy")
plt.show()

test_accuracy=[]
losses =[]
predictions = []
real = []
model.eval()
with torch.no_grad():
  loss_test=0
  for batch_val in tqdm(test_loader):
    test_id = batch_val[0].to(device)
    test_am = batch_val[1].to(device)
    test_img = batch_val[2].to(device)
    test_label = batch_val[3].to(device)
    ots = model(test_img,test_id,test_am)
    loss = criterion(ots,test_label)
    loss_test+=loss.item()
    _,pred = ots.max(1)
    predictions.extend(pred.cpu().numpy())
    real.extend(test_label.cpu().numpy())
    correct = pred.eq(test_label).sum().item()
    total = test_label.size(0)
  acc = 100*(correct/total)
  test_accuracy.append(acc)
  losses.append(loss_test)

test_accuracy=[]
losses =[]
predictions = []
real = []
model.eval()
with torch.no_grad():
  loss_test=0
  for batch_val in tqdm(test_loader):
    test_id = batch_val[0].to(device)
    test_am = batch_val[1].to(device)
    test_img = batch_val[2].to(device)
    test_label = batch_val[3].to(device)
    ots = model(test_img,test_id,test_am)
    loss = criterion(ots,test_label)
    loss_test+=loss.item()
    _,pred = ots.max(1)
    predictions.extend(pred.cpu().numpy())
    real.extend(test_label.cpu().numpy())
    correct = pred.eq(test_label).sum().item()
    total = test_label.size(0)
  acc = 100*(correct/total)
  test_accuracy.append(acc)
  losses.append(loss_test)

from sklearn.metrics import accuracy_score
from sklearn.metrics import precision_score
from sklearn.metrics import recall_score
from sklearn.metrics import f1_score
from sklearn.metrics import classification_report

print("Precision score - ", precision_score(real,predictions))

print("Recall score - ", recall_score(real,predictions))

print("F1 score - ", f1_score(real,predictions))

print("Accuracy score - ", accuracy_score(real,predictions))

print("Classification Report - \n", classification_report(real,predictions))

import pickle

# assume filename is the name of the pickle file
filename = '/content/sample_details.pkl'

# open the file in binary mode and read the data
with open(filename, 'rb') as f:
    data = pickle.load(f)

# print the loaded data
print(data)



sample_text_ids = []
for i in range(len(data)):
  x = int(data['ID'][i])
  sample_text_ids.append(x)

sample_data_text_0 = []
sample_data_label_0 = []
sample_image_path_0 = []
sample_data_text_1 = []
sample_data_label_1 = []
sample_image_path_1 = []
for i in range(len(test['id'])):
  if(test['id'][i] in sample_text_ids ):
    if(test['label'][i]==0):
      sample_data_text_0.append(test['text'][i])
      sample_data_label_0.append(test['label'][i])
      sample_image_path_0.append(test['img'][i])
    elif(test['label'][i]==1):
      sample_data_text_1.append(test['text'][i])
      sample_data_label_1.append(test['label'][i])
      sample_image_path_1.append(test['img'][i])



sample_dataset_0 = Custom_Dataset(sample_image_path_0,sample_data_text_0,sample_data_label_0, transforms=train_transforms)
sample_loader_0 = DataLoader(sample_dataset_0, batch_size=len(sample_image_path_0), shuffle=False)

sample_dataset_1 = Custom_Dataset(sample_image_path_1,sample_data_text_1,sample_data_label_1, transforms=train_transforms)
sample_loader_1 = DataLoader(sample_dataset_1, batch_size=len(sample_image_path_1), shuffle=False)

batch_0 = next(iter(sample_loader_0))
batch_1 = next(iter(sample_loader_1))

test_id_0 = batch_0[0].to(device)
test_am_0 = batch_0[1].to(device)
test_img_0 = batch_0[2].to(device)
labels_0 = batch_0[3].to(device)
ots = model(test_img_0,test_id_0,test_am_0)

test_id_1 = batch_1[0].to(device)
test_am_1 = batch_1[1].to(device)
test_img_1 = batch_1[2].to(device)
labels_1 = batch_1[3].to(device)
ots = model(test_img_1,test_id_1,test_am_1)

len(labels)

features_0 = model.get_features(test_img_0, test_id_0, test_am_0)
features_1 = model.get_features(test_img_1, test_id_1, test_am_1)

F_0 = features_0.cpu()
labels_0 = labels_0.cpu()

F_1 = features_1.cpu()
labels_1 = labels_1.cpu()

import matplotlib.pyplot as plt
from sklearn.manifold import TSNE
tsne = TSNE(n_components=2, perplexity=30.0, n_iter=1000, random_state=42)
embeddings_0 = tsne.fit_transform(F_0)
embeddings_1 = tsne.fit_transform(F_1)

plt.scatter(embeddings_0[:,0], embeddings_0[:, 1], label='non-Hateful')
plt.scatter(embeddings_1[:, 0], embeddings_1[:, 1], label='Hateful')
plt.title('t-SNE plot of features')
plt.legend()
plt.show()

model

torch.save(model.state_dict(), "/content/drive/MyDrive/multimodel.pt")

model.load_state_dict(torch.load('/content/drive/MyDrive/multimodel.pt'))

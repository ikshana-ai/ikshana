import matplotlib.pyplot as plt
import numpy as np
import torch
import seaborn as sn

from .norm import UnNormalize
from .gradcam import GradCAM, _visualize_cam


class Results():

    def __init__(self, model, loader, device, mean, std, class_list):
        self.model = model
        self.loader = loader
        self.device = device
        self.mean = mean.to(self.device)
        self.std = std.to(self.device)
        self.class_list = class_list
        self.results = self._forwad_pass()

    def _forwad_pass(self):
        '''
        Private Function to Run the Model for Inference on the Test Loader
        provided, so multiple Plot can utulize same Inferenced data.
        '''
        nb_classes = len(self.class_list)
        confusion_matrix = torch.zeros(nb_classes, nb_classes, dtype=torch.long)

        l = ['incorrect_imgs', 'incorrect_pred', 'incorrect_gt',
                'correct_imgs', 'correct_pred', 'correct_gt']
        res = dict.fromkeys(l, torch.tensor(()).to(self.device))

        self.model.eval()
        with torch.no_grad():
            for images, labels in self.loader:
                images, labels = images.to(self.device), labels.to(self.device)
                output = self.model(images)
                predicted = output.argmax(dim=1)

                # Confusion Matrix
                for l,p in zip(labels, predicted):
                    confusion_matrix[l, p] += 1

                # Getting the ids of Correct Classified Images
                idx_cor = predicted.eq(labels)
                if idx_cor.sum().item() > 0: # If there are Correct images
                    res['correct_imgs'] = torch.cat((res['correct_imgs'], images[idx_cor]), dim=0)
                    res['correct_pred'] = torch.cat((res['correct_pred'], predicted[idx_cor])).to(torch.int64)
                    res['correct_gt'] = torch.cat((res['correct_gt'], labels[[idx_cor]])).to(torch.int64)

                # Geeting the ids of "In"correct Classigied Images
                idx = ~predicted.eq(labels)
                if idx.sum().item() > 0: # If there are incorrect images
                    res['incorrect_imgs'] = torch.cat((res['incorrect_imgs'], images[idx]), dim=0)
                    res['incorrect_pred'] = torch.cat((res['incorrect_pred'], predicted[idx])).to(torch.int64)
                    res['incorrect_gt'] = torch.cat((res['incorrect_gt'], labels[[idx]])).to(torch.int64)


        cls_acc = (confusion_matrix.diag()/confusion_matrix.sum(1))*100

        res['confusion'] = confusion_matrix
        res['class_acc'] = cls_acc

        return res

    def plot_batch(self, **kwargs):
        '''
        The Function Plot the Inference of a Correctly Classified Images.

        Args:
            nrow: Number of Rows in the Plot
            ncol: Number of Coloumns in the Plot
        '''
        ncol = kwargs.get('ncol', 6)
        nrow = kwargs.get('nrow', 6)
        figsize = kwargs.get('figsize', (10,10))
        
        unNorm= UnNormalize(self.mean, self.std)

        fig,a =  plt.subplots(nrow,ncol,figsize= figsize)
        for num in range(nrow*ncol):
            if self.results['correct_imgs'][num].size(0) == 1: #Single Channel
                img = unNorm(self.results['correct_imgs'][num])
                img = torch.squeeze(img,0)
                cmap='gray'
            else: # Multi-Channel
                img = unNorm(self.results['correct_imgs'][num])
                img = np.transpose(img.cpu(), (1,2,0))
                cmap=None
            a.ravel()[num].imshow(img, cmap)
            a.ravel()[num].set_title(f"GT:{self.class_list[self.results['correct_gt'][num]]}")
            a.ravel()[num].text(0.5,-0.2, f"Predicted: {self.class_list[self.results['correct_pred'][num].item()]}", size=12, ha="center", transform=a.ravel()[num].transAxes)
            a.ravel()[num].axis('off')

        fig.tight_layout()

    def plot_incorrect(self, **kwargs):
        '''
        Plot those Incorrect classified Images in ncol*nrow matrix if given,
        or else Displays all incorrect classified Images.
        Parameters:
            nrow: The Number of Rows of Images
            ncol: The Number of Coloumns of Images
        '''
        ncol = kwargs.get('ncol', 6)
        nrow = kwargs.get('nrow', 6)
        figsize = kwargs.get('figsize', (10,10))

        unNorm = UnNormalize(self.mean, self.std)
        ncol_ = int(np.sqrt(self.results['incorrect_imgs'].size(0))) #Finding Total Number of Images Sqrt
        
        # All Images or Given ncol*nrow number of Images
        ncol = min(ncol_, ncol)
        nrow = min(ncol, nrow)

        fig,a =  plt.subplots(nrow,ncol,figsize=figsize)
        for num in range(nrow*ncol):
            if self.results['incorrect_imgs'][num].size(0) == 1: #Single Channel
                img = unNorm(self.results['incorrect_imgs'][num])
                img = torch.squeeze(img,0)
                cmap='gray'
            else: # Multi-Channel
                img = unNorm(self.results['incorrect_imgs'][num])
                img = np.transpose(img.cpu(), (1,2,0))
                cmap=None
            a.ravel()[num].imshow(img, cmap)
            a.ravel()[num].set_title(f"GT:{self.class_list[self.results['incorrect_gt'][num]]}")
            a.ravel()[num].text(0.5,-0.2, f"Predicted: {self.class_list[self.results['incorrect_pred'][num].item()]}", size=12, ha="center", transform=a.ravel()[num].transAxes)
            a.ravel()[num].axis('off')

        fig.tight_layout()

    def class_accuracy(self, confusion_heatmap=True, top_n=10, **kwargs):
        '''
        Plot a Confusion Matrix and Prints Class Wise Accuracies.

        Args:
            confusion_heatman: BOOL, To Plot Confusion HeatMap or Not.
            top_n: Class wise Accuracies to Top N **Mis-classified** Classes.
        '''
        figsize = kwargs.get('figsize', (10,10))

        if confusion_heatmap:
            plt.figure(figsize=figsize)
            sn.heatmap(self.results['confusion'].numpy(), 
                        xticklabels=self.class_list, yticklabels=self.class_list,
                        annot=True,cmap='Blues', fmt='d')
            plt.xlabel("Predicted") 
            plt.ylabel("Labels") 
            plt.show()
        
        sorted_class_acc = torch.sort(self.results['class_acc'])
        
        print(f'Accuracies of Top {top_n} Classes in Decreasing Order')
        for i in sorted_class_acc.indices[:top_n]:
            print(f"Accuracy of class {self.class_list[i]} is {self.results['class_acc'][i]:.2f}")


    def plot_gradcam(self, layer='layer4', correct= False, class_ids= False, batch_size= 64, 
                        hm_lay= 0.5, img_lay= 0.5, alpha= 1.0, **kwargs):
        '''
        Plot the Grad CAM for Incorrect Images with respect to either
        the correct class or the predicted (wrong) class.
        '''

        ncol = kwargs.get('ncol', 6)
        nrow = kwargs.get('nrow', 6)
        figsize = kwargs.get('figsize', (10,10))

        grad = GradCAM(self.model, layer)

        # if bs is greater than the no. of incorrect images.
        # if batch_size > len(self.results['incorrect_imgs']):
        #    batch_size = int(np.sqrt(self.results['incorrect_imgs'].size(0)))**2

        # To Plot For Correctly Classified Images or Mis Classified Images 
        if correct:
            images = self.results['correct_imgs']
            gt_labels = self.results['correct_gt']
        else:
            images = self.results['incorrect_imgs']
            gt_labels = self.results['incorrect_gt']
        
        batch_images = images[:batch_size,:,:,:]

        # Actual Labels for Correct Classified
        if class_ids and correct:
            class_ids = self.results['correct_gt'][:batch_size]
        # For Actual Labels for In-Correct Clasified
        elif class_ids and (not correct):
            class_ids = self.results['incorrect_gt'][:batch_size]

        mask, output_labels = grad(batch_images, class_ids)

        unNorm = UnNormalize(self.mean, self.std)
        batch_images = [unNorm(img).unsqueeze(0) for img in batch_images]
        batch_images = torch.cat(batch_images, dim=0)

        heat_map, combined_image = _visualize_cam(mask, batch_images, hm_lay, img_lay, alpha)
        
        # Selecting the Minimum ncol and nrow, to avoid no of images < subplots.
        ncol = min(int(np.sqrt(batch_size)), ncol)
        nrow = min(ncol, nrow)

        fig,a =  plt.subplots(nrow,ncol,figsize=figsize)

        cls_text = 'Predicted' if class_ids is False else 'Actual'
        cor_text = 'Correctly' if correct else 'Mis'
        fig.suptitle(f"Grad-CAM of {cor_text} Classified Images with respect to {cls_text} Class", fontsize=20)
        for num in range(nrow*ncol):
            img = combined_image[num].cpu().numpy().transpose(1,2,0)
            a.ravel()[num].imshow(img)
            a.ravel()[num].set_title(f"GT:{self.class_list[gt_labels[num]]}", fontsize=10)
            a.ravel()[num].text(0.5,-0.1, f"Predicted: {self.class_list[output_labels[num].item()]}", size=10, ha="center", transform=a.ravel()[num].transAxes)
            a.ravel()[num].axis('off')

        fig.tight_layout()
        fig.subplots_adjust(top=0.93)

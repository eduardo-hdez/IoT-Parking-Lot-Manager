from ultralytics import YOLO
import torch
import os

# Check system
print(f"\nPyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    device = 0
else:
    print("Using CPU (training will be slower)")
    device = 'cpu'

# Verify dataset
data_yaml = "./parking-dataset/data.yaml"
if not os.path.exists(data_yaml):
    print(f"\n ERROR: {data_yaml} not found!")
    print("Make sure you created the data.yaml file in parking-dataset/")
    exit(1)

print(f"\nDataset config found: {data_yaml}")

# Load pretrained model
print("\nLoading YOLOv8 nano model...")
model = YOLO('yolov8n.pt')

print("STARTING TRAINING...")
print("\nThis may take 1-3 hours on CPU, 10-30 minutes on GPU")
print("Press Ctrl+C to stop early (model will still be saved)\n")

# Train the model
try:
    results = model.train(
        data=data_yaml,
        epochs=100,           # Number of training cycles
        imgsz=320,            # Image size (smaller = faster)
        batch=16,             # Batch size (reduce if memory error)
        patience=20,          # Early stopping patience
        device=device,        # CPU or GPU
        
        # Project settings
        project='runs/detect',
        name='parking_detector',
        exist_ok=True,
        
        # Optimization for small objects
        mosaic=1.0,           # Mosaic augmentation
        mixup=0.1,            # Mixup augmentation
        scale=0.3,            # Scale augmentation
        flipud=0.5,           # Flip up-down
        fliplr=0.5,           # Flip left-right
        degrees=5,            # Rotation
        translate=0.1,        # Translation
        
        # Save settings
        save=True,
        save_period=10,       # Save checkpoint every 10 epochs
        
        # Visualization
        plots=True,
        
        # Verbosity
        verbose=True,
    )
    
    print("TRAINING COMPLETED SUCCESSFULLY!")
    
    # Show where model is saved
    best_model_path = "./runs/detect/parking_detector/weights/best.pt"
    print(f"\n Best model saved at:")
    print(f"   {os.path.abspath(best_model_path)}")
    
    print(f"\n Training results saved at:")
    print(f"   {os.path.abspath('./runs/detect/parking_detector/')}")
    
    print("\n View training charts:")
    print(f"   - Confusion matrix: ./runs/detect/parking_detector/confusion_matrix.png")
    print(f"   - Results: ./runs/detect/parking_detector/results.png")
    print(f"   - Training batches: ./runs/detect/parking_detector/train_batch0.jpg")
    
except KeyboardInterrupt:
    print("\n\n  Training interrupted by user")
    print("Partial model saved, you can resume training later")
    
except Exception as error:
    print(f"\n ERROR during training: {error}")
    print("\nTroubleshooting:")
    print("  - If memory error: Reduce batch size to 8 or 4")
    print("  - If path error: Check data.yaml has correct absolute path")
    print("  - If CUDA error: Set device='cpu' in train settings")
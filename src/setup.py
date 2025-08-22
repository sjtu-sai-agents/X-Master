from setuptools import setup, find_packages

setup(
    name='llm_agent',  
    version='0.1.0',          
    description='implementation of the llm agnet framework',  
    author='Shuo Tang',       
    author_email='tanshuo@sjtu.edu.cn',  
    packages=find_packages(), 
    install_requires=[        
        # 'numpy>=1.18.0',
        # 'requests>=2.25.1',
        'openai>=1.13.0',
    ],
    classifiers=[             
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.9',  
)
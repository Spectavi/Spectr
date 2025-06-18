from textual.screen import Screen
from textual.widgets import Static

GHOST = """
                                                             ..:::.                                 
                                                     .:::::::      :::::::.                         
                                                 .::::.                  .::::                      
                                               :::                           .:::                   
                                             :::                                :::                 
                                           :::                                    .::               
                                         .::                   :::::::              :::             
                                        .:.                          :::              ::            
                                       .::                        :::: ::              ::           
                                      .::                        ::::::              :::            
                                      ::                         ::::::           :::               
                                     ::                          ::::::         :::                 
                   :::::::::::::::  ::                            ::::       :::                    
                                    ::                                     ::                       
                                    ::                                  :::                         
          ::::::::::::::::::::::   ::                                :::                           
                                   ::                             .:::                              
                                  ::                             ::                                
              ::::::::::::::::    ::      .                        :::                              
                                 ::       :                          :::                            
                                ::       :                              :::                         
                              .::       :                                  :::                      
                             ::.      ::                                     :::.                   
                          .:::      .:.                                         :::                 
                      .::::.      .::                 :                            ::               
              ::::::::.         ::.                  :.                            ::               
               ::.          .::                     :.                            ::                
                .::                                :.                ..          ::                 
                   :::                           ::                  :         .:.                  
                      :::::::::                .:.                 .:         ::.                   
                              ::              ::                  ::        .::                     
                              .:.           ::                   ::        ::.                      
                             .::         ::.                    :.       :::                        
                            ::.                               ::        ::                          
                           ::              .::::::          .:        ::                            
                           ::       ..:::::      ::       .:       .::.                             
                             ::::::::            ::              :::.                               
                                                ::            .:::                                  
                                               ::::::::::::::::                                     
"""


class SplashScreen(Screen):
    """Center-screen logo while data initialises."""

    def __init__(self) -> None:
        super().__init__(id="splash")


    def compose(self):
        yield Static(GHOST, id="logo-art", classes="center")
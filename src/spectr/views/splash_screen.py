from textual.widget import Widget
from textual.app import ComposeResult
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


class SplashScreen(Widget):
    """Center-screen logo while data initialises."""

    def __init__(self) -> None:
        super().__init__(id="splash")

    def compose(self) -> ComposeResult:
        yield Static(GHOST, id="logo-art", classes="center")
